# ETF轮动策略 v3.3 - PTrade版本（跨境ETF延迟开盘修复）
# ==============================
#
# 【策略概述】
# 基于动量效应选择ETF，通过EPO优化权重降低风险
#
# 【交易规则】
# - 调仓周期：每月初
# - 持仓数量：3只（动量得分>0的前3只）
# - 权重分配：EPO优化
# - 交易时间：14:40之前的任意时间（先卖出，下一分钟买入）
# - 重试机制：调仓当天多分钟重试，确保成交
# - 10:30二次尝试：跨境ETF延迟开盘时智能等待
# - 资金上限：g.capital_ratio 控制策略可用资金比例
#
# 【v3.3更新】
# - **修复跨境ETF延迟开盘问题**：
#   - 发现513100.SS（纳指ETF）等跨境ETF在10:30开盘（非9:30）
#   - 新增跨境ETF列表：g.cross_border_etfs，明确哪些ETF延迟开盘
#   - 智能判断失败原因：区分"未开盘"和"停牌/数据异常"
#     * 跨境ETF + 时间<10:30 + 价格失败 → 未开盘 → 设置retry_flag等待10:30
#     * 普通ETF + 价格失败 → 停牌/数据异常 → 标记跳过，不等待10:30
# - **新增调仓重试机制**：
#   - 月初调仓当天，14:40之前每分钟检查是否需要重试
#   - 如果买入失败（价格获取失败或订单未成交），自动重试
#   - 跨境ETF失败时智能等待10:30二次尝试
# - **优化日志输出**：
#   - 区分失败原因，日志更清晰
#   - 重试次数统计，方便诊断
#
# 【v3.2更新】
# - 多策略持仓校验模块集成：启动时全局校验账户-持仓一致性
# - 精细化清理：合法持仓保留，不合法持仓删除，池外持仓删除
# - 持久化字段扩展：新增strategy_name、pool_config字段
# - 子目录名称简化：etf_rotation/（与strategy_name一致）
# - 回测模式跳过校验：避免无意义的全局校验开销
#
# ==================== PTrade适配要点 ====================
#
# 1. 股票代码格式
#    - 上海：.SS（如 518880.SS）
#    - 深圳：.SZ（如 159915.SZ）
#    - 指数：.XBHS（如 399101.XBHS）
#
# 2. API使用准则（重要！）
#    - 交易时获取价格：data[etf].price（实盘最准确）
#    - 策略因子计算：get_history（动量、EPO等）
#    - 盘前预计算：get_history（复权因子、昨收价）
#
# 3. 复权处理
#    - data[etf].price 返回除权价格
#    - 前复权价格 = 除权价格 * 复权因子
#    - 复权因子 = 前复权价 / 除权价（盘前计算）
#
# 4. 下单方式
#    - 卖出：order(etf, -shares) 按股数，需拆单
#    - 买入：order_value(etf, value) 按金额
#
# 5. 拆单处理
#    - 单笔最大90万股（留10%安全边际）
#    - 卖出：按股数拆单
#    - 买入：order_value可能自动拆单，保险起见按金额拆单
#
# 6. 跨境ETF特殊处理（v3.3新增）
#    - 跨境ETF定义：跟踪海外指数的ETF，开盘时间延迟到10:30（非9:30）
#    - 跨境ETF列表：g.cross_border_etfs = ['513100.SS', '159740.SZ']
#    - 智能判断失败原因：
#      * 跨境ETF + 时间<10:30 + 价格失败 → "未开盘" → 设置retry_flag等待10:30
#      * 普通ETF + 价格失败 → "停牌/数据异常" → 标记跳过，不等待10:30
#    - 优化重试效率：普通ETF立即跳过，跨境ETF智能等待
#
# ==================== 文件信息 ====================
#
# 版本：v3.3（跨境ETF延迟开盘修复+重试机制）
# 更新日期：2026-06-01
# 路径：D:\linux\ai_quant\quant_project\PtradeEgs\etf_rotation_strategy.py
#
# ==============================

import numpy as np
import pandas as pd
import math
import json
import uuid
from scipy.linalg import solve


# ============ 持仓追踪辅助函数 ============
def _is_owned(code):
    """判断ETF是否被本策略持有"""
    return code in g.owned_positions

def _get_owned_amount(code, context):
    """获取本策略持有数量 min(virtual, real)"""
    if code not in g.owned_positions:
        return 0
    virtual = g.owned_positions[code]
    real = context.portfolio.positions.get(code)
    real_amount = real.amount if real else 0
    return min(virtual, real_amount)

def _get_owned_enable_amount(code, context):
    """获取本策略可卖数量 min(virtual, real_enable)"""
    if code not in g.owned_positions:
        return 0
    virtual = g.owned_positions[code]
    pos = context.portfolio.positions.get(code)
    if pos is None:
        return 0
    real_enable = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
    return min(virtual, real_enable)

def _sync_owned_positions_from_account(context):
    """初始化时同步账户持仓到owned_positions"""
    for code, pos in context.portfolio.positions.items():
        if pos.amount > 0:
            g.owned_positions[code] = pos.amount
    log.info("[初始化] 同步账户持仓到owned_positions: %d只" % len(g.owned_positions))

def _sync_owned_positions(context):
    """盘前同步：删除实际已清仓的条目，更新数量"""
    removed = []
    for code in list(g.owned_positions.keys()):
        pos = context.portfolio.positions.get(code)
        if pos is None or pos.amount <= 0:
            removed.append(code)
            del g.owned_positions[code]
        else:
            g.owned_positions[code] = min(g.owned_positions[code], pos.amount)
    if removed:
        log.info("[持仓追踪] 清理已清仓: %s" % ','.join(removed))


# ============ 多策略持仓校验模块（内联版本，源自shared_position_validator.py）============
# 注意：PTrade禁止sys/os/exec，无法动态导入，必须内联
# 变更流程：先修改shared_position_validator.py，再同步到各策略

# ========== 池校验器注册表 ============
POOL_VALIDATORS = {}

def register_pool_validator(pool_type, validator_func):
    """注册池类型校验器"""
    POOL_VALIDATORS[pool_type] = validator_func

def _validate_static_pool(pool_config, code):
    """静态池校验：直接判断列表"""
    pool_list = pool_config.get('value', [])
    if not isinstance(pool_list, list):
        return False
    return code in pool_list

def validate_pool_membership(pool_config, code, context=None):
    """通用池成员校验"""
    pool_type = pool_config.get('type', 'unknown')
    validator = POOL_VALIDATORS.get(pool_type)

    if validator is None:
        return True  # 未知池类型，默认通过

    # 静态池不需要额外参数
    return validator(pool_config, code)

# 注册静态池校验器
register_pool_validator('static', _validate_static_pool)

def collect_account_positions(context):
    """从账户获取真实持仓"""
    account_positions = {}
    try:
        for code, pos in context.portfolio.positions.items():
            amount = getattr(pos, 'amount', 0)
            if amount > 0:
                account_positions[code] = amount
    except Exception:
        pass
    return account_positions

def validate_per_stock(account_positions, all_strategy_states):
    """逐股票校验合法性（规则：账户份额 >= 策略份额总和）"""
    validation_result = {}

    # 收集所有策略涉及的股票代码
    all_codes = set()
    for strategy_name, state_info in all_strategy_states.items():
        owned_positions = state_info.get('owned_positions', {})
        all_codes.update(owned_positions.keys())

    # 逐股票校验
    for code in all_codes:
        account_amount = account_positions.get(code, 0)
        strategy_sum = 0
        strategy_details = {}

        for strategy_name, state_info in all_strategy_states.items():
            owned_positions = state_info.get('owned_positions', {})
            amount = owned_positions.get(code, 0)
            if amount > 0:
                strategy_sum += amount
                strategy_details[strategy_name] = amount

        is_valid = (account_amount >= strategy_sum)
        validation_result[code] = {
            'valid': is_valid,
            'account_amount': account_amount,
            'strategy_sum': strategy_sum,
            'strategies': strategy_details
        }

    return validation_result

def clean_current_strategy(current_strategy_name, pool_config, validation_result, context=None, log_func=None):
    """清理当前策略持仓，返回合法持仓"""
    valid_positions = {}

    if log_func is None:
        log_func = print

    for code, result in validation_result.items():
        current_amount = result['strategies'].get(current_strategy_name, 0)
        if current_amount <= 0:
            continue

        # 规则1：全局校验通过
        if not result['valid']:
            log_func("[校验] %s 账户份额%d < 策略总和%d，不合法，删除"
                     % (code, result['account_amount'], result['strategy_sum']))
            continue

        # 规则2：股票池校验
        if not validate_pool_membership(pool_config, code, context):
            log_func("[校验] %s 不在当前策略股票池内，删除" % code)
            continue

        # 规则3：取min(账户实际, 持久化记录)
        account_amount = result['account_amount']
        final_amount = min(current_amount, account_amount)
        valid_positions[code] = final_amount
        log_func("[校验] %s 合法，保留%d股" % (code, final_amount))

    return valid_positions

def validate_strategy_positions(context, strategy_name, pool_config, owned_positions,
                                all_strategy_states_data=None, log_func=None, is_trade_func=None):
    """校验当前策略持仓（主API入口）"""
    if log_func is None:
        log_func = print

    # 回测模式跳过校验
    if is_trade_func is not None:
        try:
            if not is_trade_func():
                log_func("[校验] 回测模式，跳过全局校验")
                return owned_positions
        except Exception:
            pass

    # 如果没有传入其他策略数据，只做池校验
    if all_strategy_states_data is None:
        log_func("[校验] 无其他策略数据，仅执行池校验")
        valid_positions = {}
        for code, amount in owned_positions.items():
            if validate_pool_membership(pool_config, code, context):
                valid_positions[code] = amount
                log_func("[校验-池] %s 在池内，保留" % code)
            else:
                log_func("[校验-池] %s 不在池内，删除" % code)
        return valid_positions

    # 全局校验流程
    all_strategy_states = all_strategy_states_data if all_strategy_states_data else {}

    if strategy_name not in all_strategy_states:
        all_strategy_states[strategy_name] = {
            'owned_positions': owned_positions,
            'pool_config': pool_config
        }
    else:
        all_strategy_states[strategy_name]['owned_positions'] = owned_positions

    log_func("[校验] 收到%d个策略数据" % len(all_strategy_states))

    account_positions = collect_account_positions(context)
    log_func("[校验] 账户持仓: %d只" % len(account_positions))

    validation_result = validate_per_stock(account_positions, all_strategy_states)

    valid_positions = clean_current_strategy(
        strategy_name, pool_config, validation_result, context, log_func
    )

    original_count = len(owned_positions)
    valid_count = len(valid_positions)
    removed_count = original_count - valid_count

    log_func("[校验完成] 原持仓%d只 → 合法%d只，删除%d只"
             % (original_count, valid_count, removed_count))

    return valid_positions


# ============ 持久化函数（独立策略子目录）============
def _get_state_dir():
    """获取本策略专属数据目录（独立子目录，防止与其他策略混淆）"""
    base_path = get_research_path()
    strategy_dir = "etf_rotation/"  # 简化目录名（策略名称）
    create_dir(strategy_dir)
    return base_path + strategy_dir

def _get_state_file_path():
    """获取状态文件路径"""
    return _get_state_dir() + "state.json"

def _save_state(context):
    """保存策略状态"""
    state = {
        'version': 2,  # 版本升级（支持校验模块）
        'strategy_name': g.strategy_name,  # 策略名称（新增）
        'pool_config': g.pool_config,  # 股票池配置（新增）
        'saved_date': context.blotter.current_dt.strftime('%Y-%m-%d'),
        'strategy_uuid': g.strategy_uuid,
        'owned_positions': g.owned_positions,
        'last_trade_month': g.last_trade_month,
    }
    path = _get_state_file_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    log.info("[状态持久化] 保存成功 → %s" % path)

def _load_state(context):
    """加载持久化状态，恢复UUID、owned_positions、last_trade_month等"""
    path = _get_state_file_path()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            state = json.load(f)

        version = state.get('version', 1)

        # 兼容version 1和version 2
        loaded_uuid = state.get('strategy_uuid')
        if loaded_uuid:
            g.strategy_uuid = loaded_uuid

        loaded_owned = state.get('owned_positions', {})
        if isinstance(loaded_owned, dict):
            g.owned_positions = loaded_owned

        loaded_month = state.get('last_trade_month', -1)
        if isinstance(loaded_month, int):
            g.last_trade_month = loaded_month

        # version 2新增字段
        if version >= 2:
            loaded_name = state.get('strategy_name')
            if loaded_name:
                g.strategy_name = loaded_name
            loaded_pool = state.get('pool_config')
            if loaded_pool and isinstance(loaded_pool, dict):
                g.pool_config = loaded_pool

        log.info("[状态持久化] 恢复成功(v%d): uuid=%s, owned=%d只, last_month=%d"
                 % (version, g.strategy_uuid, len(g.owned_positions), g.last_trade_month))
    except Exception as e:
        log.info("[状态持久化] 无状态文件或加载失败: %s" % str(e))


def _clear_state_file():
    """清空持久化文件（回测开始时调用，避免干扰实盘）"""
    path = _get_state_file_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{}')
        log.info("[清理] 持久化文件已清空: %s" % path)
    except Exception as e:
        log.info("[清理] 无法清空文件: %s" % str(e))


# ============ 初始化函数 ============
def initialize(context):
    # ===== 1. 策略信息声明（多策略校验模块使用）=====
    g.strategy_name = 'etf_rotation'  # 策略名称（子目录名）
    g.pool_config = {'type': 'static', 'value': []}  # 股票池配置（ET池稍后设置）

    # ===== 1. 持仓追踪变量（先设置默认值）=====
    g.strategy_uuid = None  # 首次启动后生成，持久化恢复
    g.owned_positions = {}  # {etf_code: amount} 持仓追踪
    g.last_trade_month = -1  # 上次调仓月份（持久化恢复）

    # ===== 2. 加载持久化状态 =====
    _load_state(context)

    # ===== 3. 如果UUID仍为None，首次启动生成 =====
    if g.strategy_uuid is None:
        g.strategy_uuid = uuid.uuid4().hex[:8]
        log.info("[初始化] 首次启动，生成UUID: %s" % g.strategy_uuid)

    # ===== 4. 全局持仓校验（多策略并行时使用）=====
    # ETF池定义（校验需要股票池）
    g.etf_pool = [
        # 商品
        '518880.SS',  # 黄金ETF
        '159985.SZ',  # 豆粕ETF
        # 海外
        '513100.SS',  # 纳指ETF
        # 宽基
        '510300.SS',  # 沪深300ETF
        '159915.SZ',  # 创业板
        # 窄基
        '159992.SZ',  # 创新药ETF
        '515700.SS',  # 新能车ETF
        '510150.SS',  # 消费ETF
        '515790.SS',  # 光伏ETF
        '515880.SS',  # 通信ETF
        '512720.SS',  # 计算机ETF
        '512660.SS',  # 军工ETF
        '159740.SZ',  # 恒生科技ETF
    ]
    g.pool_config['value'] = g.etf_pool  # 更新股票池配置

    # ===== 4.1 跨境ETF列表（10:30开盘，非9:30）=====
    # 注意：跨境ETF跟踪海外指数，开盘时间延迟到10:30
    g.cross_border_etfs = [
        '513100.SS',   # 纳指ETF（纳斯达克100指数）
        '159740.SZ',   # 恒生科技ETF（恒生科技指数）
    ]

    # 调用校验模块（仅实盘模式，校验函数已内联到本文件）
    # 注意：PTrade禁止sys/os/exec，校验函数已内联
    # 变更流程：先修改shared_position_validator.py，再同步到各策略
    if is_trade():
        try:
            # 直接调用内联的校验函数（已在本文件中定义）
            log.info("[校验] 开始执行持仓校验...")
            g.owned_positions = validate_strategy_positions(
                context,
                g.strategy_name,
                g.pool_config,
                g.owned_positions,
                log_func=log.info,
                is_trade_func=is_trade
            )
            # 保存校验后的合法持仓
            _save_state(context)
            log.info("[校验] 校验完成，合法持仓: %d只" % len(g.owned_positions))
        except Exception as e:
            log.warning("[校验] 校验失败: %s，使用原始持仓" % str(e))
            # 如果owned_positions为空，同步账户持仓（fallback）
            if len(g.owned_positions) == 0:
                _sync_owned_positions_from_account(context)
                if len(g.owned_positions) > 0:
                    log.warning("[初始化] owned_positions为空，已同步账户持仓，这些持仓将被本策略管理")
    else:
        # 回测模式：如果owned_positions为空，不同步（回测从头开始）
        if len(g.owned_positions) == 0:
            log.info("[回测] owned_positions为空，从空仓开始")

    # 设置股票池（g.etf_pool已在上文定义）
    set_universe(g.etf_pool)

    # 设置基准
    set_benchmark('000300.XSHG')

    # 策略参数
    g.stock_num = 3
    g.m_days = 34
    g._lambda = 10
    g.w = 0.2

    # ==================== 资金上限参数 ====================
    g.capital_ratio = 0.2  # 策略可用资金比例（20%，双策略验证）
    log.info("[资金上限] 策略可用资金比例: %.0f%%" % (g.capital_ratio * 100))

    # ==================== 跨境ETF特殊处理（v3.3新增）====================
    log.info("[跨境ETF] 10:30开盘: %s" % ','.join(g.cross_border_etfs))
    log.info("[跨境ETF] 智能判断失败原因，延迟开盘自动等待10:30重试")

    # 调仓控制
    # g.last_trade_month 已通过_load_state恢复
    g.trade_done_today = False
    g.sell_done = False
    g.buy_done = False

    # 目标ETF信息
    g.target_etfs = []
    g.target_weights = []
    g.etf_weight_map = {}

    # 回测设置
    if not is_trade():
        _clear_state_file()  # 回测开始清理持久化，避免干扰实盘
        log.info("[回测] 清理持久化文件")
        set_backtest()

    log.info("=== 策略初始化完成 UUID: %s ===" % g.strategy_uuid)


# ============ 设置回测条件 ============
def set_backtest():
    set_limit_mode('UNLIMITED')
    set_commission(commission_ratio=0.0002, min_commission=5.0)
    set_slippage(slippage=0.002)


# ============ 盘前处理 ============
def before_trading_start(context, data):
    g.current_date = context.blotter.current_dt.strftime('%Y-%m-%d')
    g.trade_done_today = False
    g.sell_done = False
    g.buy_done = False
    g.buy_retry_flag = False  # 跨境ETF失败重试标志（v3.3新增）
    g.target_etfs = []
    g.target_weights = []
    g.etf_weight_map = {}

    # ========== 盘前同步owned_positions ==========
    _sync_owned_positions(context)

    # ========== 盘前日志：调仓判断 ==========
    current_month = context.blotter.current_dt.month
    need_rebalance = current_month != g.last_trade_month

    log.info("=" * 60)
    log.info("【盘前铃声】日期: %s" % g.current_date)
    log.info("-" * 60)

    # 当前持仓状态
    owned_list = [etf for etf in g.owned_positions if _get_owned_amount(etf, context) > 0]
    log.info(">>> 当前持仓: %d只" % len(owned_list))
    for etf in owned_list:
        amount = _get_owned_amount(etf, context)
        log.info("    [%s] %d股" % (etf, amount))
    if not owned_list:
        log.info("    (空仓)")

    # 调仓判断
    log.info("-" * 60)
    log.info(">>> 调仓判断: 当前月份=%d, 上次调仓月份=%d" % (current_month, g.last_trade_month))
    if need_rebalance:
        log.info("    结论: 月初调仓，需执行")
    else:
        log.info("    结论: 非月初，不调仓")

    # ========== 盘前预计算（交易时不再调用get_history）==========
    # 1. 前复权因子：盘中用 data[etf].price * 因子 得到前复权价格
    # 2. 昨收价：用于涨停判断
    g.fq_factor = {}       # 前复权因子
    g.yesterday_close = {} # 昨天前复权收盘价（用于涨停判断）

    log.info("-" * 60)
    log.info(">>> 预计算复权因子")
    for etf in g.etf_pool:
        try:
            # 获取昨天的除权价格和前复权价格
            his_raw = get_history(1, frequency='1d', field='close', security_list=etf, fq=None, include=False, is_dict=True)
            raw_price = his_raw[etf]['close'][-1] if his_raw and etf in his_raw else 0

            his_fq = get_history(1, frequency='1d', field='close', security_list=etf, fq='pre', include=False, is_dict=True)
            fq_price = his_fq[etf]['close'][-1] if his_fq and etf in his_fq else 0

            if raw_price > 0 and fq_price > 0:
                g.fq_factor[etf] = fq_price / raw_price
                g.yesterday_close[etf] = fq_price  # 昨天前复权收盘价
                log.info("    [%s] 除权价=%.3f, 前复权价=%.3f, 因子=%.4f" % (etf, raw_price, fq_price, g.fq_factor[etf]))
            else:
                g.fq_factor[etf] = 1.0
                g.yesterday_close[etf] = 0
                log.warning("    [%s] 无法计算，使用默认因子1.0" % etf)
        except Exception as e:
            g.fq_factor[etf] = 1.0
            g.yesterday_close[etf] = 0
            log.error("    [%s] 计算异常: %s" % (etf, str(e)))

    log.info("=" * 60)


# ============ 盘中处理 ============
def handle_data(context, data):
    current_time = context.blotter.current_dt.strftime('%H:%M')
    current_month = context.blotter.current_dt.month
    
    # ==================== 调仓判断 ====================
    if current_month != g.last_trade_month and current_time < '14:40' and not g.trade_done_today:
        
        # ========== 阶段1：卖出（第一分钟） ==========
        if not g.sell_done:
            log.info("=" * 60)
            log.info("【月初调仓】时间: %s" % current_time)
            log.info("-" * 60)

            # ========== 使用owned_positions获取当前持仓 ==========
            hold_list = [etf for etf in g.owned_positions if _get_owned_amount(etf, context) > 0]

            # 计算目标ETF
            target_list = get_rank(g.etf_pool)
            if not target_list:
                log.warning("无法获取目标ETF，跳过调仓")
                g.last_trade_month = current_month
                g.trade_done_today = True
                return

            result = run_optimization(target_list)
            if not result:
                log.warning("无法计算权重，跳过调仓")
                g.last_trade_month = current_month
                g.trade_done_today = True
                return

            g.target_etfs = target_list
            g.target_weights = result['weights']
            g.etf_weight_map = {etf: g.target_weights[i] for i, etf in enumerate(g.target_etfs)}

            total_value = context.portfolio.total_value
            cash = context.portfolio.cash

            # ==================== 资金上限计算 ====================
            strategy_capital = total_value * g.capital_ratio
            log.info("-" * 60)
            log.info(">>> 调仓计划")
            log.info("    总资产=%.2f | 策略可用=%.2f | 现金=%.2f" % (total_value, strategy_capital, cash))
            log.info(">>> 目标池: %s" % ','.join(g.target_etfs))
            for i, etf in enumerate(g.target_etfs):
                w = g.target_weights[i]
                target_amt = strategy_capital * w
                log.info("    [%s] 权重=%.2f%% | 目标金额=%.2f" % (etf, w * 100, target_amt))

            log.info(">>> 当前持仓: %d只" % len(hold_list))
            for etf in hold_list:
                owned_amount = _get_owned_amount(etf, context)
                if owned_amount > 0:
                    log.info("    [%s] %d股" % (etf, owned_amount))
            if not hold_list:
                log.info("    (空仓)")

            # 执行卖出（带拆单）
            log.info("-" * 60)
            log.info(">>> 卖出阶段开始")

            # ========== 卖出统计变量 ==========
            sell_count = 0
            total_sell_shares = 0
            cleared_count = 0

            for etf in hold_list:
                try:
                    # ========== 使用辅助函数获取持仓数量 ==========
                    owned_amount = _get_owned_amount(etf, context)
                    owned_enable = _get_owned_enable_amount(etf, context)
                    if owned_amount <= 0:
                        continue

                    etf_converted = etf.replace('.XSHG', '.SS').replace('.XSHE', '.SZ')
                    weight = g.etf_weight_map.get(etf_converted, 0)

                    # ========== 使用 data[etf].price 获取前复权价格 ==========
                    raw_price = data[etf].price if hasattr(data[etf], 'price') else 0
                    fq_factor = g.fq_factor.get(etf, 1.0)
                    price = raw_price * fq_factor

                    log.info("    [%s] 实时价=%.3f, 复权因子=%.4f, 前复权价=%.3f" % (etf, raw_price, fq_factor, price))

                    # 计算目标股数（使用策略可用资金）
                    if weight <= 0 or etf_converted not in g.target_etfs:
                        # 清仓：全部卖出
                        sell_shares = owned_enable
                        log.info("    [%s] 清仓 %d股（不在目标池）" % (etf, sell_shares))
                    elif price <= 0:
                        log.error("    [%s] 无法获取价格，跳过" % etf)
                        sell_shares = 0
                    else:
                        # 减仓：计算目标股数（基于策略可用资金）
                        target_shares = int(strategy_capital * weight / price / 100) * 100
                        if owned_amount > target_shares:
                            sell_shares = min(owned_amount - target_shares, owned_enable)
                            log.info("    [%s] 减仓 %d股（当前=%d，目标=%d）" % (etf, sell_shares, owned_amount, target_shares))
                        else:
                            sell_shares = 0
                            log.info("    [%s] 无需减仓（当前=%d ≤ 目标=%d）" % (etf, owned_amount, target_shares))

                    # 拆单卖出
                    if sell_shares > 0:
                        remaining = sell_shares
                        while remaining > 0:
                            batch = min(remaining, 900000)  # 单笔最大90万股
                            batch = int(batch / 100) * 100
                            if batch > 0:
                                order(etf, -batch)
                                remaining -= batch
                            else:
                                if remaining > 0:
                                    order(etf, -remaining)  # 剩余不足100股，一次卖出
                                break

                        # ========== 更新统计 ==========
                        sell_count += 1
                        total_sell_shares += sell_shares

                        # ========== 更新owned_positions ==========
                        new_owned = owned_amount - sell_shares
                        if new_owned <= 0:
                            cleared_count += 1
                            if etf in g.owned_positions:
                                del g.owned_positions[etf]
                        else:
                            g.owned_positions[etf] = new_owned
                        log.info("    [%s] 卖出成功，剩余=%d股" % (etf, new_owned))

                except Exception as e:
                    log.error("    [%s] 卖出异常: %s" % (etf, str(e)))

            # ========== 卖出阶段汇总 ==========
            log.info("-" * 60)
            log.info(">>> 卖出完成：共卖出%d只ETF，合计%d股，清仓%d只" % (sell_count, total_sell_shares, cleared_count))
            log.info("=" * 60)

            g.sell_done = True
            return
        
        # ========== 阶段2：买入（第二分钟） ==========
        if g.sell_done and not g.buy_done:
            log.info("-" * 60)
            log.info(">>> 买入阶段开始")

            total_value = context.portfolio.total_value
            cash = context.portfolio.cash

            # ==================== 资金上限计算 ====================
            strategy_capital = total_value * g.capital_ratio
            log.info("    总资产=%.2f | 策略可用=%.2f | 现金=%.2f" % (total_value, strategy_capital, cash))

            # ========== 买入统计变量 ==========
            buy_count = 0
            total_buy_value = 0
            skipped_count = 0

            for i, etf in enumerate(g.target_etfs):
                w = g.target_weights[i]
                if w <= 0:
                    continue

                # 目标金额 = 策略可用资金 * 权重
                target_value = strategy_capital * w

                # ========== 使用辅助函数获取当前持仓 ==========
                current_shares = _get_owned_amount(etf, context)

                # 涨停检查
                skip_buy = False
                price = 0
                yesterday_close = 0

                # ========== 使用盘前预存的昨收价，交易时不调用get_history ==========
                try:
                    # 获取实时价格（除权价）
                    raw_price = data[etf].price if hasattr(data[etf], 'price') else 0

                    # 获取复权因子（盘前已计算）
                    fq_factor = g.fq_factor.get(etf, 1.0)

                    # 计算前复权价格
                    price = raw_price * fq_factor

                    # 获取昨收价（盘前已计算）
                    yesterday_close = g.yesterday_close.get(etf, 0)

                    log.info("    [%s] 实时价=%.3f | 复权因子=%.4f | 前复权=%.3f" % (etf, raw_price, fq_factor, price))
                except Exception as e:
                    log.error("    [%s] 获取价格异常: %s" % (etf, str(e)))

                if price <= 0:
                    # 判断失败原因：区分"未开盘"和"停牌/数据异常"
                    current_time = context.blotter.current_dt.strftime('%H:%M')
                    is_cross_border = etf in g.cross_border_etfs  # 是否跨境ETF

                    if is_cross_border and current_time < '10:30':
                        # 跨境ETF未开盘（10:30才开盘）
                        log.warning("    [%s] 无法获取价格（跨境ETF未开盘，等待10:30重试）" % etf)
                        g.buy_retry_flag = True  # 设置重试标志，等待10:30二次尝试
                        skipped_count += 1
                        continue
                    else:
                        # 普通ETF或10:30之后仍无法获取价格 → 停牌/数据异常
                        log.error("    [%s] 无法获取价格（停牌或数据异常，跳过）" % etf)
                        skipped_count += 1
                        continue

                # ========== 计算当前市值 ==========
                current_value = current_shares * price if current_shares > 0 else 0

                # 涨停判断
                try:
                    code = etf.split('.')[0]
                    limit_rate = 0.20 if code.startswith('688') or code.startswith('300') else 0.10

                    up_limit = yesterday_close * (1 + limit_rate)

                    if price >= up_limit * 0.995:
                        skip_buy = True
                        log.warning("    [%s] 涨停中，跳过（昨收=%.3f，涨停价=%.3f）" % (etf, yesterday_close, up_limit))
                        skipped_count += 1
                except Exception as e:
                    log.error("    [%s] 涨停判断异常: %s" % (etf, str(e)))

                if skip_buy:
                    continue

                # 计算需要买入的金额
                need_buy_value = target_value - current_value

                if need_buy_value <= 100:
                    log.info("    [%s] 无需买入（目标=%.2f，当前=%.2f，差额=%.2f）" % (etf, target_value, current_value, need_buy_value))
                    continue

                # 实际买入金额（不超过可用资金）
                actual_buy_value = min(need_buy_value, cash)

                if actual_buy_value < 100:
                    log.warning("[买入] %s: 资金不足，跳过 (可用=%.2f)" % (etf, cash))
                    continue

                # 计算单笔最大金额（90万股 * 价格，留5%安全边际）
                max_value_per_order = 900000 * price * 0.95 if price > 0 else 500000

                # 拆单买入（按金额）
                remaining_value = actual_buy_value
                order_count = 0
                while remaining_value > 0:
                    batch_value = min(remaining_value, max_value_per_order)
                    if batch_value > 0:
                        order_value(etf, batch_value)
                        order_count += 1
                        remaining_value -= batch_value
                    else:
                        break

                log.info("[买入] %s: 下单 %d 笔，共 %.2f 元" % (etf, order_count, actual_buy_value))

                # ========== 更新计数器 ==========
                buy_count += 1
                total_buy_value += actual_buy_value

                # ========== 更新owned_positions（估算买入股数）==========
                estimated_shares = int(actual_buy_value / price / 100) * 100 if price > 0 else 0
                if estimated_shares > 0:
                    if etf in g.owned_positions:
                        g.owned_positions[etf] += estimated_shares
                    else:
                        g.owned_positions[etf] = estimated_shares
                    log.info("[买入] %s: 估算买入%d股, owned_positions更新为%d股" % (etf, estimated_shares, g.owned_positions[etf]))

                # 更新剩余资金
                cash -= actual_buy_value

            # ========== 买入阶段汇总 ==========
            log.info("-" * 60)
            log.info(">>> 买入完成: 成功买入%d只 | 总金额%.2f元 | 跳过%d只"
                     % (buy_count, total_buy_value, skipped_count))
            log.info("    剩余现金: %.2f元" % cash)
            log.info("=" * 60)

            g.buy_done = True
            g.trade_done_today = True
            g.last_trade_month = current_month

    # ========== 10:30二次尝试机制（跨境ETF延迟开盘，v3.3新增）==========
    # 如果月初调仓时遇到跨境ETF失败（未开盘），10:30之后重试买入
    elif g.buy_retry_flag and '10:30' <= current_time < '14:40' and not g.buy_done:
        log.info("=" * 60)
        log.info("[10:30二次尝试] 时间: %s | 跨境ETF已开盘，重试买入" % current_time)
        log.info("=" * 60)

        # 重试买入阶段（逻辑与上面的买入阶段一致）
        log.info("-" * 60)
        log.info(">>> 买入重试阶段开始")

        total_value = context.portfolio.total_value
        cash = context.portfolio.cash

        # 资金上限计算
        strategy_capital = total_value * g.capital_ratio
        log.info("    总资产=%.2f | 策略可用=%.2f | 现金=%.2f" % (total_value, strategy_capital, cash))

        # 买入统计变量
        buy_count = 0
        total_buy_value = 0
        skipped_count = 0

        for i, etf in enumerate(g.target_etfs):
            w = g.target_weights[i]
            if w <= 0:
                continue

            # 目标金额 = 策略可用资金 * 权重
            target_value = strategy_capital * w

            # 获取当前持仓
            current_shares = _get_owned_amount(etf, context)

            # 获取价格（此时跨境ETF已开盘）
            price = 0
            skip_buy = False

            try:
                # 获取实时价格（除权价）
                raw_price = data[etf].price if hasattr(data[etf], 'price') else 0

                # 获取复权因子
                fq_factor = g.fq_factor.get(etf, 1.0)

                # 计算前复权价格
                price = raw_price * fq_factor

                log.info("    [%s] 实时价=%.3f | 复权因子=%.4f | 前复权=%.3f" % (etf, raw_price, fq_factor, price))
            except Exception as e:
                log.error("    [%s] 获取价格异常: %s" % (etf, str(e)))

            if price <= 0:
                # 10:30之后仍无法获取价格，真正停牌或数据异常
                log.error("    [%s] 无法获取价格（停牌或数据异常，跳过）" % etf)
                skipped_count += 1
                continue

            # 计算当前市值
            current_value = current_shares * price if current_shares > 0 else 0

            # 计算需要买入的金额
            need_buy_value = target_value - current_value

            if need_buy_value <= 100:
                log.info("    [%s] 无需买入（目标=%.2f，当前=%.2f，差额=%.2f）" % (etf, target_value, current_value, need_buy_value))
                continue

            # 实际买入金额
            actual_buy_value = min(need_buy_value, cash)

            if actual_buy_value < 100:
                log.warning("[买入重试] %s: 资金不足，跳过 (可用=%.2f)" % (etf, cash))
                continue

            # 拆单买入
            max_value_per_order = 900000 * price * 0.95
            remaining_value = actual_buy_value
            order_count = 0

            while remaining_value > 0:
                batch_value = min(remaining_value, max_value_per_order)
                if batch_value > 0:
                    order_value(etf, batch_value)
                    order_count += 1
                    remaining_value -= batch_value
                else:
                    break

            log.info("[买入重试] %s: 下单 %d 笔，共 %.2f 元" % (etf, order_count, actual_buy_value))
            buy_count += 1
            total_buy_value += actual_buy_value
            cash -= actual_buy_value

            # 更新持仓追踪（下单后立即记录，假设成交）
            # 注意：实际成交数量需要在后续重试检查中确认
            g.owned_positions[etf] = current_shares + int(actual_buy_value / price / 100) * 100

        log.info(">>> 买入重试完成: 成功买入%d只 | 总金额%.2f元 | 跳过%d只"
                 % (buy_count, total_buy_value, skipped_count))
        log.info("    剩余现金: %.2f元" % cash)
        log.info("=" * 60)

        # 清除重试标志，标记完成
        g.buy_retry_flag = False
        g.buy_done = True
        g.trade_done_today = True


# ============ 盘后处理 ============
def after_trading_end(context, data):
    """盘后同步+持久化"""
    _sync_owned_positions(context)

    # 实盘才保存状态，回测不保存
    if is_trade():
        _save_state(context)
        log.info("[盘后] 实盘持久化完成")
    else:
        log.info("[盘后] 回测模式，不持久化")

    # ========== 盘后持仓汇总 ==========
    total_value = context.portfolio.total_value
    cash = context.portfolio.cash
    positions_value = total_value - cash
    strategy_capital = total_value * g.capital_ratio

    owned_list = list(g.owned_positions.keys())

    log.info("=" * 60)
    log.info("【盘后汇总】日期: %s" % g.current_date)
    log.info("-" * 60)

    # 资金状况
    log.info(">>> 资金状况")
    log.info("    总资产: %.2f元" % total_value)
    log.info("    现金: %.2f元" % cash)
    log.info("    持仓市值: %.2f元" % positions_value)
    log.info("    策略可用资金: %.2f元 (比例=%.0f%%)"
             % (strategy_capital, g.capital_ratio * 100))

    # 本策略持仓明细
    log.info("-" * 60)
    log.info(">>> 本策略持仓: %d只" % len(owned_list))
    for etf in owned_list:
        amount = g.owned_positions.get(etf, 0)
        # 计算持仓市值
        try:
            price = data[etf].price if hasattr(data[etf], 'price') else 0
            fq_factor = g.fq_factor.get(etf, 1.0)
            fq_price = price * fq_factor
            value = amount * fq_price if amount > 0 else 0
            log.info("    [%s] %d股 | 市值=%.2f元 | 价格=%.3f"
                     % (etf, amount, value, fq_price))
        except:
            log.info("    [%s] %d股" % (etf, amount))

    if not owned_list:
        log.info("    (空仓)")

    log.info("=" * 60)


# ============ 动量因子计算 ============
def get_rank(etf_pool):
    """基于年化收益和判定系数打分的动量因子轮动"""
    score_list = []
    
    for etf in etf_pool:
        his = get_history(g.m_days, frequency='1d', field='close', 
                          security_list=etf, fq='pre', include=False, is_dict=True)
        
        if his is None or etf not in his:
            continue
        
        close_array = his[etf]['close']
        
        if len(close_array) < g.m_days:
            continue
        
        # 计算动量得分
        y = np.log(close_array)
        x = np.arange(len(y))
        slope, intercept = np.polyfit(x, y, 1)
        annualized_returns = math.pow(math.exp(slope), 250) - 1
        r_squared = 1 - (sum((y - (slope * x + intercept))**2) / ((len(y) - 1) * np.var(y, ddof=1)))
        score = annualized_returns * r_squared
        score_list.append({'etf': etf, 'score': score})
    
    # 排序
    df = pd.DataFrame(score_list)
    if df.empty:
        return []
    
    df = df.sort_values(by='score', ascending=False)
    
    # 筛选得分>0的
    filtered_list = df[df['score'] > 0]['etf'].tolist()[:g.stock_num]
    return filtered_list


# ============ EPO优化函数 ============
def epo(x, signal, lambda_, method='simple', w=None, anchor=None, normalize=True, endogenous=True):
    """EPO权重优化"""
    n = x.shape[1]
    
    vcov = x.cov()
    corr = x.corr()
    
    I = np.eye(n)
    V = np.zeros((n, n))
    np.fill_diagonal(V, vcov.values.diagonal())
    std = np.sqrt(V)
    
    s = signal.values if hasattr(signal, 'values') else signal
    a = anchor.values if hasattr(anchor, 'values') else anchor

    shrunk_cor = ((1 - w) * I @ corr.values) + (w * I)
    cov_tilde = std @ shrunk_cor @ std
    inv_shrunk_cov = solve(cov_tilde, np.eye(n))

    if method == 'simple':
        epo_weights = (1 / lambda_) * inv_shrunk_cov @ s
    elif method == 'anchored':
        if endogenous:
            num = np.sqrt(a.T @ cov_tilde @ a)
            denom = np.sqrt(s.T @ inv_shrunk_cov @ cov_tilde @ inv_shrunk_cov @ s)
            gamma = num / denom
            
            term1 = (1 - w) * gamma * s
            term2 = w * I @ V @ a
            
            combined = term1 + term2
            
            epo_weights = inv_shrunk_cov @ combined
        else:
            epo_weights = inv_shrunk_cov @ (((1 - w) * (1 / lambda_) * s) + ((w * I @ V @ a)))

    if normalize:
        epo_weights = [0 if weight < 0 else weight for weight in epo_weights]
        epo_weights = np.array(epo_weights) / np.sum(epo_weights)

    return epo_weights


# ============ 获取数据并调用优化 ============
def run_optimization(stocks):
    """获取数据并调用EPO优化"""
    # 获取价格数据（前复权）
    his = get_history(1200, frequency='1d', field='close', 
                      security_list=stocks, fq='pre', include=False, is_dict=True)
    
    if his is None:
        log.error("获取价格数据失败")
        return None
    
    # 构建DataFrame
    close_data = {}
    for etf in stocks:
        if etf in his:
            close_data[etf] = his[etf]['close']
    
    if not close_data:
        log.error("无有效价格数据")
        return None
    
    # 找到最短长度，对齐数据
    min_len = min(len(arr) for arr in close_data.values())
    
    # 对齐所有数组到相同长度
    close_data_aligned = {}
    for etf, arr in close_data.items():
        close_data_aligned[etf] = arr[-min_len:]
    
    close_prices = pd.DataFrame(close_data_aligned)
    
    # 按列名排序（与聚宽pivot行为一致）
    close_prices = close_prices.reindex(sorted(close_prices.columns), axis=1)
    
    # 计算收益率
    returns = close_prices.pct_change().dropna()
    
    # 计算锚定权重
    d = np.diag(returns.cov())
    a = (1/d) / (1/d).sum()
    
    # 调用EPO
    try:
        weights = epo(x=returns, signal=returns.mean(), lambda_=g._lambda, method='anchored', w=g.w, anchor=a)
        return {'weights': weights, 'columns': list(close_prices.columns)}
    except Exception as e:
        log.error("EPO优化失败: %s" % (str(e)))
        return None
