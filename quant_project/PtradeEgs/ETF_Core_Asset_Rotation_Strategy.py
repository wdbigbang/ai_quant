# ETF核心资产轮动策略（安全摸狗策略）v1.5.2 - PTrade版本
# ==============================
#
# 【策略概述】
# 每日选择动量得分最高的1只ETF满仓持有，追求简单高效
#
# 【交易规则】
# - 盘前选股：09:00前完成动量计算，确定目标ETF
# - 开盘调仓：09:30开盘即执行买卖（使用盘前选股结果）
# - 重试机制1：09:31-35每分钟检查，未成交则重试（最多4次）
# - 二次尝试：10:30-35专门处理跨境ETF延迟开盘（如纳指ETF 513100）
# - 重试机制2：10:30-35每分钟检查，未成交则重试（最多4次）
# - **盘中成交确认**（v1.5.1新增）：交易时间每分钟检查成交情况，避免遗漏
# - **盘后强制同步**（v1.5.1新增）：盘后从账户真实持仓强制同步，确保owned_positions准确
# - 持仓数量：仅1只（动量得分最高且在安全区间内）
# - 动量计算：加权线性回归（25天，近期权重更大）
# - 打分公式：年化收益 × R²
# - 安全区过滤：score > 0 且 <= 5（避免追高风险）
# - 资金上限：g.capital_ratio 控制策略可用资金比例
#
# 【v1.5.2更新】（跨境ETF卖出bug修复）
# - **修复严重bug：跨境ETF卖出时owned_positions立即删除，导致持仓不一致**
#   - 问题：跨境ETF（如513100.SS纳指ETF）10:30开盘，但策略9:30尝试卖出
#   - 原因：卖出逻辑没有对齐买入的保护机制，立即删除owned_positions
#   - 解决方案：对齐买入逻辑的完整保护机制
#     1. 卖出订单跟踪：新增g.sell_orders列表记录卖出订单
#     2. 跨境ETF判断：卖出前检查开盘时间，识别"未开盘"vs"停牌"
#     3. 延迟删除：等待成交确认后才删除owned_positions
#     4. 成交确认：check_and_retry()检查卖出成交，未成交则重试
#     5. 盘后同步：after_trading_end()处理未确认的卖出订单
# - **优化卖出保护机制**：
#   - 卖出前判断跨境ETF开盘时间，智能处理"未开盘"场景
#   - 10:30二次尝试触发条件扩展：增加卖出失败检查
#   - 盘后强制同步卖出订单：确保owned_positions与实际持仓一致
#
# 【v1.5.1更新】（持仓追踪bug修复）
# - **修复严重bug：买入成交后持仓未被记录**
#   - 问题：用户在11:12买入，下单成功成交，但owned_positions为空
#   - 原因：重试机制只在09:31-35和10:30-35触发，其他时间买入后成交确认遗漏
#   - 解决方案：三重保障机制
#     1. 盘中成交确认：交易时间（09:30-15:00）每分钟检查下单记录的成交情况
#     2. 盘后强制同步：盘后检查账户真实持仓，强制更新owned_positions
#     3. 账户持仓对照：盘后汇总显示账户真实持仓，对比策略追踪持仓，发现不一致时警告
# - **优化日志输出**：
#   - 盘后强制同步日志：清晰提示持仓同步情况
#   - 账户真实持仓显示：标记池内/池外，方便诊断
#   - 不一致警告：及时发现持久化问题
#
# 【v1.5更新】
# - **修复跨境ETF延迟开盘问题**：
#   - 发现513100.SS（纳指100）等跨境ETF在10:30开盘（非9:30）
#   - 新增跨境ETF列表：g.cross_border_etfs，明确哪些ETF延迟开盘
#   - 智能判断失败原因：区分"未开盘"和"停牌/数据异常"
#     * 跨境ETF + 时间<10:30 + 价格失败 → 未开盘 → 触发10:30二次尝试
#     * 普通ETF + 价格失败 → 停牌/数据异常 → 不触发10:30二次尝试（只在9:31-35重试）
#   - 修复：trade()和check_and_retry()函数中价格获取失败时智能判断
# - **完善10:30二次尝试机制**：
#   - 改为4次重试机制（10:30-35每分钟重试一次）
#   - 与9:31-35重试机制保持一致，应对开盘流动性不足
#   - 买入+卖出全面检查，确保调仓完成
# - **优化重试效率**：
#   - 普通ETF失败立即在9:31-35重试，不浪费时间等到10:30
#   - 跨境ETF失败智能等待10:30二次尝试，避免无效重试
#
# 【v1.4更新】
# - 多策略持仓校验模块集成：启动时全局校验账户-持仓一致性
# - 精细化清理：合法持仓保留，不合法持仓删除，池外持仓删除
# - 持久化字段扩展：新增strategy_name、pool_config字段
# - 回测模式跳过校验：避免无意义的全局校验开销
#
# 【v1.3更新】
# - 选股提前到盘前（before_trading_start）执行
# - 开盘时直接使用盘前选股结果进行买卖，无需等待选股计算
# - 提高实盘响应速度，减少开盘延迟
#
# 【v1.2更新】
# - 调仓时间提前到09:30开盘即执行
# - 新增重试机制：09:31-35每分钟检查未成交订单并重试（最多4次）
# - 增强实盘可靠性，应对开盘流动性不足等异常情况
#
# 【v1.1更新】
# - 移除涨停判断逻辑，严格对齐JoinQuant原版
# - 添加详细日志输出（动量得分、安全区过滤、资金状况、买卖详情）
# - 保留持仓追踪UUID标记、持久化处理、90万股拆单、资金上限
#
# ==================== PTrade适配要点 ====================
#
# 1. 股票代码格式
#    - 上海：.SS（如 518880.SS）
#    - 深圳：.SZ（如 159915.SZ）
#
# 2. API使用准则（重要！）
#    - 动量计算：get_history（盘前预计算）
#    - 交易时获取价格：data[etf].price（实盘最准确）
#    - 买入：order_value(etf, value) 按金额
#    - 卖出：order(etf, -shares) 按股数，需拆单
#
# 3. 调度方式
#    - 原版：run_daily(trade, '9:30')
#    - PTrade：盘前选股 + handle_data开盘交易 + 重试机制 + 10:30二次尝试
#
# 4. 跨境ETF特殊处理（v1.5新增）
#    - 跨境ETF定义：跟踪海外指数的ETF，开盘时间延迟到10:30（非9:30）
#    - 跨境ETF列表：g.cross_border_etfs = ['513100.SS', ...]
#    - 智能判断失败原因：
#      * 跨境ETF + 时间<10:30 + 价格失败 → "未开盘" → 触发10:30二次尝试
#      * 普通ETF + 价格失败 → "停牌/数据异常" → 不触发10:30二次尝试
#    - 优化重试效率：普通ETF立即重试，跨境ETF智能等待
#
# ==================== 文件信息 ====================
#
# 版本：v1.5.2（跨境ETF卖出bug修复）
# 更新日期：2026-06-02
# 路径：D:\linux\ai_quant\ai_quant\quant_project\PtradeEgs\ETF_Core_Asset_Rotation_Strategy.py
#
# ==============================

import numpy as np
import pandas as pd
import math
import json
import uuid


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

def _check_account_positions(context):
    """检查账户持仓状态，记录日志提醒（不同步到owned_positions）

    重要：本策略不从账户同步持仓，owned_positions只来源于：
    1. 持久化文件恢复（实盘重启）
    2. 本策略买入时添加
    """
    total_positions = len([code for code, pos in context.portfolio.positions.items() if pos.amount > 0])

    if total_positions > 0 and len(g.owned_positions) == 0:
        log.warning("[初始化] 账户有%d只持仓，但本策略owned_positions为空" % total_positions)
        log.warning("    这些持仓可能是其他策略或手动交易，本策略不会管理")
        log.warning("    如果这些持仓属于本策略，请检查持久化文件是否丢失")
    elif total_positions > len(g.owned_positions):
        other_count = total_positions - len(g.owned_positions)
        log.info("[初始化] 账户有%d只持仓，本策略追踪%d只，其他%d只（不管理）"
                 % (total_positions, len(g.owned_positions), other_count))

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
    strategy_dir = "etf_core_asset_rotation/"
    create_dir(strategy_dir)
    return base_path + strategy_dir

def _get_state_file_path():
    """获取状态文件路径"""
    return _get_state_dir() + "state.json"

def _clear_state_file():
    """清空持久化文件（回测开始时调用，避免干扰实盘）"""
    path = _get_state_file_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{}')
        log.info("[清理] 持久化文件已清空: %s" % path)
    except Exception as e:
        log.info("[清理] 无法清空文件: %s" % str(e))

def _save_state(context):
    """保存策略状态"""
    state = {
        'version': 2,  # 版本升级（支持校验模块）
        'strategy_name': g.strategy_name,  # 策略名称（新增）
        'pool_config': g.pool_config,  # 股票池配置（新增）
        'saved_date': context.blotter.current_dt.strftime('%Y-%m-%d'),
        'strategy_uuid': g.strategy_uuid,
        'owned_positions': g.owned_positions,
        'last_trade_date': g.last_trade_date,
    }
    path = _get_state_file_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    log.info("[状态持久化] 保存成功 → %s" % path)

def _load_state(context):
    """加载持久化状态"""
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

        loaded_date = state.get('last_trade_date', '')
        if isinstance(loaded_date, str):
            g.last_trade_date = loaded_date

        # version 2新增字段
        if version >= 2:
            loaded_name = state.get('strategy_name')
            if loaded_name:
                g.strategy_name = loaded_name
            loaded_pool = state.get('pool_config')
            if loaded_pool and isinstance(loaded_pool, dict):
                g.pool_config = loaded_pool

        log.info("[状态持久化] 恢复成功(v%d): uuid=%s, owned=%d只, last_date=%s"
                 % (version, g.strategy_uuid, len(g.owned_positions), g.last_trade_date))
    except Exception as e:
        log.info("[状态持久化] 无状态文件或加载失败: %s" % str(e))


# ============ 动量计算函数 ============
def MOM(etf):
    """加权线性回归动量计算

    使用加权线性回归计算年化收益，权重线性增加（近期权重更大）
    打分公式：年化收益 × R²（拟合优度）

    返回：score, annualized_returns, r_squared
    """
    try:
        his = get_history(g.m_days, frequency='1d', field='close',
                          security_list=etf, fq=None, include=False, is_dict=True)

        if his is None or etf not in his:
            log.warning("[MOM] %s: 无法获取历史数据" % etf)
            return -999, 0, 0

        close_arr = his[etf]['close']
        if len(close_arr) < g.m_days:
            log.warning("[MOM] %s: 数据不足（%d < %d）" % (etf, len(close_arr), g.m_days))
            return -999, 0, 0

        # 加权线性回归
        y = np.log(close_arr)
        n = len(y)
        x = np.arange(n)
        weights = np.linspace(1, 2, n)  # 线性增加权重（近期权重更大）

        slope, intercept = np.polyfit(x, y, 1, w=weights)
        annualized_returns = math.pow(math.exp(slope), 250) - 1

        # 计算R²（加权残差）
        residuals = y - (slope * x + intercept)
        weighted_residuals = weights * residuals**2
        r_squared = 1 - (np.sum(weighted_residuals) / np.sum(weights * (y - np.mean(y))**2))

        score = annualized_returns * r_squared

        return score, annualized_returns, r_squared

    except Exception as e:
        log.error("[MOM] %s: 计算异常 %s" % (etf, str(e)))
        return -999, 0, 0


# ============ 选股函数 ============
def get_rank(etf_pool):
    """基于动量得分排序，安全区间过滤

    安全区过滤：score > 0 且 <= 5
    - score <= 0: 无动量，不值得持有
    - score > 5: 动量过高，追高风险太大

    返回：排名列表 [{'etf': code, 'score': value, 'annual_ret': value, 'r2': value}, ...]
    """
    log.info("=" * 60)
    log.info(">>> 动量计算（天数=%d）" % g.m_days)
    log.info("-" * 60)

    score_list = []

    for etf in etf_pool:
        score, annual_ret, r2 = MOM(etf)
        score_list.append({
            'etf': etf,
            'score': score,
            'annual_ret': annual_ret,
            'r2': r2
        })

        # 详细输出每个ETF的计算结果
        if score != -999:
            log.info("    [%s] 动量得分=%.4f | 年化收益=%.2f%% | R²=%.4f"
                     % (etf, score, annual_ret * 100, r2))
        else:
            log.warning("    [%s] 动量得分=无效（数据不足）" % etf)

    df = pd.DataFrame(score_list)

    # 排序（降序）
    df = df.sort_values(by='score', ascending=False)

    log.info("-" * 60)
    log.info(">>> 动量排名（降序）")
    for idx, row in df.iterrows():
        if row['score'] != -999:
            log.info("    第%d名: [%s] 得分=%.4f" % (idx + 1, row['etf'], row['score']))

    # 安全区间过滤：score > 0 且 <= 5
    df_filtered = df[(df['score'] > 0) & (df['score'] <= 5)]

    log.info("-" * 60)
    log.info(">>> 安全区过滤（score > 0 且 <= 5）")

    if len(df_filtered) == 0:
        log.warning("    无符合条件ETF（全部得分<=0或>5）")
        log.info("    → 空仓观望")
        log.info("=" * 60)
        return []

    log.info("    符合条件%d只：" % len(df_filtered))
    for idx, row in df_filtered.iterrows():
        log.info("      [%s] 得分=%.4f（安全区）" % (row['etf'], row['score']))

    log.info("=" * 60)

    # 返回完整信息（包含得分详情）
    return df_filtered.to_dict('records')


# ============ 初始化函数 ============
def initialize(context):
    # ===== 1. 策略信息声明（多策略校验模块使用）=====
    g.strategy_name = 'etf_core_asset_rotation'  # 策略名称（子目录名）
    g.pool_config = {'type': 'static', 'value': []}  # 股票池配置（ETF池稍后设置）

    # ===== 1. 持仓追踪变量 =====
    g.strategy_uuid = None
    g.owned_positions = {}
    g.last_trade_date = ''

    # ===== 2. 回测清理持久化 =====
    if not is_trade():
        _clear_state_file()
        log.info("[回测] 清理持久化文件")

    # ===== 3. 加载持久化状态 =====
    _load_state(context)

    # ===== 4. UUID处理 =====
    if g.strategy_uuid is None:
        g.strategy_uuid = uuid.uuid4().hex[:8]
        log.info("[初始化] 首次启动，生成UUID: %s" % g.strategy_uuid)

    # ===== 5. ETF池定义 =====
    g.etf_pool = [
        '518880.SS',   # 黄金ETF（大宗商品）
        '513100.SS',   # 纳指100（海外资产）
        '159915.SZ',   # 创业板100（成长股、科技股、中小盘）
        '510180.SS',   # 上证180（价值股、蓝筹股、中大盘）
    ]
    g.pool_config['value'] = g.etf_pool  # 更新股票池配置

    # ===== 5.1 跨境ETF列表（10:30开盘，非9:30）=====
    # 注意：跨境ETF跟踪海外指数，开盘时间延迟到10:30
    g.cross_border_etfs = [
        '513100.SS',   # 纳指100（纳斯达克100指数）
        # 可扩展其他跨境ETF：
        # '513290.SS',   # 纳指生物（纳斯达克生物科技）
        # '513050.SS',   # 中概互联
        # '159509.SZ',   # 纳指科技ETF景顺
    ]

    # ===== 6. 全局持仓校验（多策略并行时使用）=====
    # 注意：PTrade禁止sys/os/exec，校验函数已内联到本文件
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
            log.warning('[校验] 校验失败: %s，使用原始持仓' % str(e))

    # ===== 7. 检查账户持仓状态（仅记录日志，不同步）=====
    _check_account_positions(context)

    # 设置股票池
    set_universe(g.etf_pool)

    # 设置基准
    set_benchmark('000300.XSHG')

    # ===== 8. 策略参数 =====
    g.m_days = 25  # 动量参考天数
    g.capital_ratio = 0.5  # 策略可用资金比例（20%，双策略验证）

    log.info("=" * 60)
    log.info("【策略初始化】v1.5.2（跨境ETF卖出bug修复）")
    log.info("-" * 60)
    log.info("    ETF池: %s" % ','.join(g.etf_pool))
    log.info("    动量天数: %d" % g.m_days)
    log.info("    持仓数量: 1只（动量最高）")
    log.info("    安全区: score > 0 且 <= 5")
    log.info("    资金比例: %.0f%%" % (g.capital_ratio * 100))
    log.info("    特殊处理: 跨境ETF（513100等）10:30开盘，自动二次尝试")
    log.info("    新增保障: 盘中成交确认 + 盘后强制同步（三重保障）")
    log.info("=" * 60)

    # ===== 9. 调仓控制 =====
    g.trade_done_today = False
    g.current_date = ''

    # ===== 买入订单状态变量 =====
    g.buy_order_value = 0     # 买入下单金额（等待确认）
    g.buy_order_price = 0     # 买入下单价格
    g.buy_order_failed = False  # 买入是否失败（停牌等）

    # ===== 卖出订单状态变量 =====
    g.sell_orders = []        # 卖出订单列表（等待确认）
                             # 格式：[{'etf': code, 'shares': n}, ...]
    g.sell_order_failed = False  # 卖出是否失败（跨境ETF未开盘等）

    # ===== 10. 回测设置 =====
    if not is_trade():
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

    # ========== 重试机制变量初始化 ==========
    g.retry_count = 0      # 重试次数计数器（09:31-35）
    g.second_round_retry_count = 0  # 10:30二次尝试计数器（10:30-35）
    g.target_etf = None    # 目标ETF（用于重试检查）
    g.trade_flag = True    # 允许交易（开盘后第一次handle_data即执行）

    # ========== 买入订单状态初始化 ==========
    g.buy_order_value = 0     # 买入下单金额（等待确认）
    g.buy_order_price = 0     # 买入下单价格
    g.buy_order_failed = False  # 买入是否失败

    # ========== 卖出订单状态初始化 ==========
    g.sell_orders = []        # 卖出订单列表（等待确认）
    g.sell_order_failed = False  # 卖出是否失败

    # 盘前同步持仓
    _sync_owned_positions(context)

    # ========== 盘前选股（提前计算，开盘直接交易）==========
    log.info("=" * 60)
    log.info("【盘前选股】日期: %s | 时间: 09:00前" % g.current_date)
    log.info("注意: 跨境ETF（513100.SS纳指100）10:30开盘，需二次尝试")
    log.info("=" * 60)

    rank_list = get_rank(g.etf_pool)
    target_info = rank_list[:1] if rank_list else []
    g.target_etf = target_info[0]['etf'] if target_info else None

    if g.target_etf:
        log.info(">>> 盘前选股结果: [%s] 得分=%.4f"
                 % (g.target_etf, target_info[0]['score']))
    else:
        log.info(">>> 盘前选股结果: 无（空仓观望）")

    # ========== 盘前日志 ==========
    log.info("=" * 60)
    log.info("【盘前铃声】日期: %s" % g.current_date)
    log.info("-" * 60)

    owned_list = list(g.owned_positions.keys())
    log.info(">>> 本策略持仓: %d只 | %s" % (len(owned_list), ','.join(owned_list) if owned_list else '空仓'))

    log.info("=" * 60)


# ============ 盘中处理 ============
def handle_data(context, data):
    # ==================== 调仓+重试机制 ====================
    # 采用官方demo模式：通过trade_flag控制，第一次handle_data即执行调仓
    # 然后在09:31-09:35期间检查是否需要重试
    # 10:30-10:35再尝试一轮（跨境ETF如纳指ETF10:30才开盘）

    current_time = context.blotter.current_dt.strftime('%H:%M')

    # 第一次调仓（开盘后第一次handle_data调用）
    if g.trade_flag and not g.trade_done_today:
        log.info("=" * 60)
        log.info("【每日调仓】日期: %s | 时间: %s | 第一次调用" % (g.current_date, current_time))
        log.info("=" * 60)

        trade(context, data)
        g.trade_done_today = True
        g.trade_flag = False  # 关闭交易flag，防止重复执行
        g.retry_count = 0     # 初始化重试计数器（09:31-35）
        g.second_round_retry_count = 0  # 初始化10:30二次尝试计数器

    # 重试机制（09:31-09:35期间，已执行过第一次调仓）
    elif '09:31' <= current_time <= '09:35' and g.trade_done_today and g.retry_count < 4:
        # 每分钟最多重试一次（通过时间检查避免同一分钟重复重试）
        last_retry_time = getattr(g, 'last_retry_time', '')
        if current_time != last_retry_time:
            g.last_retry_time = current_time
            need_retry = check_and_retry(context, data)
            if need_retry:
                g.retry_count += 1
                log.info("[重试] 第%d次重试 @ %s" % (g.retry_count, current_time))

    # 10:30二次尝试机制（跨境ETF延迟开盘，4次重试）
    elif '10:30' <= current_time <= '10:35' and g.trade_done_today and g.second_round_retry_count < 4:
        # 检查是否有买入或卖出失败的订单
        buy_order_failed = getattr(g, 'buy_order_failed', False)
        buy_order_value = getattr(g, 'buy_order_value', 0)
        sell_order_failed = getattr(g, 'sell_order_failed', False)
        sell_orders = getattr(g, 'sell_orders', [])

        if buy_order_failed or buy_order_value > 0 or sell_order_failed or sell_orders:
            # 有失败订单，尝试二次买入/卖出
            last_retry_time = getattr(g, 'last_retry_time', '')
            if current_time != last_retry_time:
                g.last_retry_time = current_time
                log.info("=" * 60)
                log.info("[10:30二次尝试] 时间: %s | 第%d次检查失败订单"
                         % (current_time, g.second_round_retry_count + 1))
                log.info("    买入失败: %s | 买入待确认: %s"
                         % (buy_order_failed, buy_order_value > 0))
                log.info("    卖出失败: %s | 卖出待确认: %d只"
                         % (sell_order_failed, len(sell_orders)))
                log.info("=" * 60)

                need_retry = check_and_retry(context, data)
                if need_retry:
                    g.second_round_retry_count += 1
                    log.info("[10:30重试] 第%d次重试完成 @ %s"
                             % (g.second_round_retry_count, current_time))

    # ========== 盘中成交确认机制（v1.5.1新增）==========
    # 解决：用户在非重试时间窗口买入后，成交确认遗漏的问题
    # 如果有下单记录（buy_order_value>0）且在交易时间，每分钟检查成交情况
    elif g.trade_done_today and '09:30' <= current_time <= '15:00':
        buy_order_value = getattr(g, 'buy_order_value', 0)
        if buy_order_value > 0 and current_time not in ['09:31', '09:32', '09:33', '09:34', '09:35', '10:30', '10:31', '10:32', '10:33', '10:34', '10:35']:
            # 有下单记录，但不在专门的重试时间窗口，检查成交
            last_retry_time = getattr(g, 'last_retry_time', '')
            if current_time != last_retry_time:
                g.last_retry_time = current_time
                # 调用成交确认检查
                check_and_retry(context, data)


def check_and_retry(context, data):
    """检查调仓是否完成，未完成则重试"""
    need_retry = False

    # ========== 1. 检查卖出成交确认（v1.5.2新增）==========
    sell_orders = getattr(g, 'sell_orders', [])
    if sell_orders:
        log.info("-" * 60)
        log.info("[卖出成交检查] 待确认卖出订单: %d只" % len(sell_orders))

        sell_confirmed = []  # 已成交的卖出订单
        for order in sell_orders[:]:  # 遍历副本
            etf = order['etf']
            shares = order['shares']

            # 检查实际持仓是否已清空
            real_pos = context.portfolio.positions.get(etf)
            actual_shares = real_pos.amount if real_pos else 0

            if actual_shares == 0:
                # 已成交清仓，删除owned_positions
                sell_confirmed.append(etf)
                if etf in g.owned_positions:
                    del g.owned_positions[etf]
                log.info("[卖出成交确认] [%s] 清仓成功，实际持仓=0" % etf)
            else:
                log.info("[卖出成交检查] [%s] 未成交，实际持仓=%d股" % (etf, actual_shares))

        # 移除已成交的订单
        for etf in sell_confirmed:
            g.sell_orders = [o for o in g.sell_orders if o['etf'] != etf]

        if sell_confirmed:
            log.info("[卖出成交确认] 成交%d只，剩余待确认%d只"
                     % (len(sell_confirmed), len(g.sell_orders)))

        # 清除卖出失败标志（所有卖出订单已确认成交）
        if not g.sell_orders:
            g.sell_order_failed = False
            log.info("[卖出成交确认] 所有卖出订单已成交，清除失败标志")

    # ========== 2. 卖出重试（v1.5.2新增）==========
    if g.sell_orders:
        need_retry = True
        log.info("-" * 60)
        log.info("[卖出重试检查] 待重试卖出: %d只" % len(g.sell_orders))

        for order in g.sell_orders[:]:  # 遍历副本
            etf = order['etf']
            expected_shares = order['shares']

            # 检查实际持仓
            real_pos = context.portfolio.positions.get(etf)
            actual_shares = real_pos.amount if real_pos else 0

            if actual_shares == 0:
                # 已成交清仓
                if etf in g.owned_positions:
                    del g.owned_positions[etf]
                g.sell_orders = [o for o in g.sell_orders if o['etf'] != etf]
                log.info("[卖出重试] [%s] 已清仓，移除订单" % etf)
                continue

            # 检查可卖数量
            owned_enable = _get_owned_enable_amount(etf, context)
            if owned_enable == 0:
                # 可卖数量为0（T+1锁定或已清仓）
                log.warning("[卖出重试] [%s] 可卖数量=0，跳过" % etf)
                continue

            # ===== 跨境ETF判断 =====
            try:
                price = data[etf].price if hasattr(data[etf], 'price') else 0
            except:
                price = 0

            current_time = context.blotter.current_dt.strftime('%H:%M')
            is_cross_border = etf in g.cross_border_etfs

            if price <= 0:
                if is_cross_border and current_time < '10:30':
                    # 跨境ETF未开盘，等待10:30
                    log.warning("[卖出重试] [%s] 跨境ETF未开盘，等待10:30二次尝试" % etf)
                    g.sell_order_failed = True
                    continue
                else:
                    # 停牌或数据异常
                    log.warning("[卖出重试] [%s] 无法获取价格（停牌或数据异常）" % etf)
                    continue

            # 重新下单卖出
            remaining = owned_enable
            while remaining > 0:
                batch = min(remaining, 900000)
                batch = int(batch / 100) * 100
                if batch > 0:
                    order(etf, -batch)
                    remaining -= batch
                else:
                    if remaining > 0:
                        order(etf, -remaining)
                    break

            log.info("[卖出重试] [%s] 重新卖出%d股" % (etf, owned_enable))

    # ========== 3. 检查卖出是否完成（原有逻辑改造）==========
    # 补充检查：如果hold_list中有不在目标池且不在sell_orders中的ETF
    # 说明是trade()遗漏的，需要补充卖出
    hold_list = [etf for etf in g.owned_positions if _get_owned_amount(etf, context) > 0]

    for etf in hold_list:
        if etf != g.target_etf:
            # 检查是否已在sell_orders中
            in_sell_orders = any(o['etf'] == etf for o in g.sell_orders)
            if not in_sell_orders:
                owned_enable = _get_owned_enable_amount(etf, context)
                if owned_enable > 0:
                    # 补充记录卖出订单
                    g.sell_orders.append({
                        'etf': etf,
                        'shares': owned_enable
                    })
                    need_retry = True
                    log.warning("[卖出检查] [%s] 发现遗漏的卖出订单，已补充记录" % etf)

    # ========== 2. 检查买入是否完成 ==========
    if g.target_etf:
        # 获取实际持仓（从账户真实持仓）
        real_pos = context.portfolio.positions.get(g.target_etf)
        actual_shares = real_pos.amount if real_pos else 0

        # 获取实时价格
        try:
            price = data[g.target_etf].price if hasattr(data[g.target_etf], 'price') else 0
        except:
            price = 0

        # 检查是否有下单记录（表示需要确认成交）
        buy_order_value = getattr(g, 'buy_order_value', 0)
        buy_order_price = getattr(g, 'buy_order_price', 0)

        if buy_order_value > 0 and actual_shares == 0:
            # 下单但未成交，可能停牌或其他问题
            need_retry = True
            log.warning("[重试检查] [%s] 下单%.2f元但未成交，可能停牌或行情异常"
                        % (g.target_etf, buy_order_value))

            # 检查是否停牌（如果价格获取失败）
            if price <= 0:
                # 判断失败原因：区分"未开盘"和"停牌/数据异常"
                current_time = context.blotter.current_dt.strftime('%H:%M')
                is_cross_border = g.target_etf in g.cross_border_etfs  # 是否跨境ETF

                if is_cross_border and current_time < '10:30':
                    # 跨境ETF未开盘（10:30才开盘）
                    log.warning("[重试检查] [%s] 无法获取价格（跨境ETF未开盘，等待10:30二次尝试）"
                                % g.target_etf)
                    need_retry = False
                    g.buy_order_failed = True  # 触发10:30二次尝试
                else:
                    # 普通ETF或10:30之后仍无法获取价格 → 停牌/数据异常
                    log.warning("[重试检查] [%s] 无法获取价格（停牌或数据异常，不触发10:30二次尝试）"
                                % g.target_etf)
                    need_retry = False
                    g.buy_order_failed = False  # 不触发10:30二次尝试
            else:
                # 尝试重试买入
                total_value = context.portfolio.total_value
                cash = context.portfolio.cash
                strategy_capital = total_value * g.capital_ratio
                actual_buy = min(strategy_capital, cash)

                if actual_buy >= 100:
                    log.info("[重试检查] [%s] 重试买入，现金=%.2f元" % (g.target_etf, cash))

                    # 拆单买入
                    max_value = 900000 * price * 0.95
                    remaining = actual_buy
                    order_count = 0

                    while remaining > 0:
                        batch = min(remaining, max_value)
                        if batch > 0:
                            order_value(g.target_etf, batch)
                            order_count += 1
                            remaining -= batch
                        else:
                            break

                    log.info("[重试] [%s] 下单%d笔，共%.2f元"
                             % (g.target_etf, order_count, actual_buy))

                    # 更新下单记录，等待下次检查确认
                    g.buy_order_value = actual_buy
                    g.buy_order_price = price

        elif buy_order_value > 0 and actual_shares > 0:
            # 下单且已成交，更新owned_positions
            need_retry = False
            g.owned_positions[g.target_etf] = actual_shares
            log.info("[重试检查] [%s] 买入成交确认，实际成交%d股" % (g.target_etf, actual_shares))
            # 清除下单记录
            g.buy_order_value = 0
            g.buy_order_price = 0
            g.buy_order_failed = False

        elif price > 0 and actual_shares == 0 and buy_order_value == 0:
            # 无下单记录但持仓为0，可能是首次检查
            need_retry = True
            log.info("[重试检查] [%s] 未买入，需重试" % g.target_etf)

            total_value = context.portfolio.total_value
            cash = context.portfolio.cash
            strategy_capital = total_value * g.capital_ratio
            actual_buy = min(strategy_capital, cash)

            if actual_buy >= 100:
                # 拆单买入
                max_value = 900000 * price * 0.95
                remaining = actual_buy
                order_count = 0

                while remaining > 0:
                    batch = min(remaining, max_value)
                    if batch > 0:
                        order_value(g.target_etf, batch)
                        order_count += 1
                        remaining -= batch
                    else:
                        break

                log.info("[重试] [%s] 下单%d笔，共%.2f元"
                         % (g.target_etf, order_count, actual_buy))

                # 记录下单，等待下次检查
                g.buy_order_value = actual_buy
                g.buy_order_price = price

    if not need_retry:
        log.info("[重试检查] 调仓已完成，无需重试")

    return need_retry


def trade(context, data):
    """执行调仓（开盘即执行，使用盘前已选好的目标ETF）"""
    g.trade_done_today = True
    g.last_trade_date = g.current_date

    log.info("=" * 60)
    log.info("【开盘调仓】日期: %s" % g.current_date)
    log.info("=" * 60)

    # ========== 1. 目标ETF（盘前已选好）==========
    target_etf = g.target_etf  # 直接使用盘前选股结果

    if target_etf:
        log.info(">>> 目标ETF: [%s]（盘前已选定）" % target_etf)
    else:
        log.info(">>> 目标ETF: 无（空仓观望）")

    # ========== 2. 资金状况 ==========
    total_value = context.portfolio.total_value
    cash = context.portfolio.cash
    strategy_capital = total_value * g.capital_ratio

    log.info("-" * 60)
    log.info(">>> 资金状况")
    log.info("    总资产: %.2f元" % total_value)
    log.info("    现金: %.2f元" % cash)
    log.info("    持仓市值: %.2f元" % (total_value - cash))
    log.info("    策略可用资金: %.2f元 (比例=%.0f%%)"
             % (strategy_capital, g.capital_ratio * 100))

    # ========== 3. 当前持仓（本策略）==========
    hold_list = [etf for etf in g.owned_positions if _get_owned_amount(etf, context) > 0]

    log.info("-" * 60)
    log.info(">>> 当前持仓（本策略）: %d只" % len(hold_list))
    for etf in hold_list:
        amount = _get_owned_amount(etf, context)
        try:
            price = data[etf].price if hasattr(data[etf], 'price') else 0
            value = amount * price if amount > 0 else 0
            log.info("    [%s] %d股 | 市值=%.2f元 | 价格=%.3f"
                     % (etf, amount, value, price))
        except:
            log.info("    [%s] %d股" % (etf, amount))

    if not hold_list:
        log.info("    (空仓)")

    # ========== 4. 卖出阶段 ==========
    log.info("-" * 60)
    log.info(">>> 卖出阶段")
    sell_count = 0
    total_sell_shares = 0

    for etf in hold_list:
        if etf != target_etf:
            # 不在目标池，卖出
            owned_enable = _get_owned_enable_amount(etf, context)
            if owned_enable > 0:
                # ===== 跨境ETF判断：未开盘则跳过 =====
                try:
                    price = data[etf].price if hasattr(data[etf], 'price') else 0
                except:
                    price = 0

                current_time = context.blotter.current_dt.strftime('%H:%M')
                is_cross_border = etf in g.cross_border_etfs

                if price <= 0 and is_cross_border and current_time < '10:30':
                    # 跨境ETF未开盘（10:30才开盘）
                    log.warning("    [%s] 无法获取价格（跨境ETF未开盘，等待10:30二次尝试）" % etf)
                    g.sell_order_failed = True  # 触发10:30二次尝试

                    # 记录卖出订单（等待成交确认）
                    g.sell_orders.append({
                        'etf': etf,
                        'shares': owned_enable
                    })
                    sell_count += 1
                    total_sell_shares += owned_enable

                    # 注意：不立即删除owned_positions，等待成交确认
                    log.info("    [%s] 卖出订单已记录，等待10:30二次尝试" % etf)
                    continue
                elif price <= 0:
                    # 普通ETF或10:30之后仍无法获取价格 → 停牌/数据异常
                    log.warning("    [%s] 无法获取价格（停牌或数据异常）" % etf)
                    # 仍记录卖出订单，等待重试
                    g.sell_orders.append({
                        'etf': etf,
                        'shares': owned_enable
                    })
                    sell_count += 1
                    total_sell_shares += owned_enable
                    log.info("    [%s] 卖出订单已记录，等待9:31-35重试" % etf)
                    continue

                # ===== 正常卖出（价格正常）=====
                # 拆单卖出（单笔最大90万股）
                remaining = owned_enable
                while remaining > 0:
                    batch = min(remaining, 900000)
                    batch = int(batch / 100) * 100
                    if batch > 0:
                        order(etf, -batch)
                        remaining -= batch
                    else:
                        if remaining > 0:
                            order(etf, -remaining)
                        break

                sell_count += 1
                total_sell_shares += owned_enable

                sell_value = owned_enable * price
                log.info("    [%s] 卖出 → 清仓%d股，市值%.2f元"
                         % (etf, owned_enable, sell_value))

                # 记录卖出订单（等待成交确认）
                g.sell_orders.append({
                    'etf': etf,
                    'shares': owned_enable
                })

                # 注意：不立即删除owned_positions，等待成交确认
                # 成交确认在check_and_retry()中处理
                log.info("    [%s] 卖出订单已记录，等待成交确认" % etf)
        else:
            log.info("    [%s] 继续持有（与目标一致）" % etf)

    if sell_count == 0:
        log.info("    无需卖出（持仓与目标一致）")
    elif sell_count > 0:
        log.info("    卖出完成: 清仓%d只，合计%d股" % (sell_count, total_sell_shares))

    # ========== 5. 买入阶段 ==========
    log.info("-" * 60)
    log.info(">>> 买入阶段")

    # 重新获取资金状况（卖出后现金已更新）
    total_value = context.portfolio.total_value
    cash = context.portfolio.cash  # 重要：卖出后重新获取现金
    strategy_capital = total_value * g.capital_ratio

    log.info("    重新获取资金: 总资产=%.2f元, 现金=%.2f元, 策略可用=%.2f元"
             % (total_value, cash, strategy_capital))

    current_shares = _get_owned_amount(target_etf, context) if target_etf else 0

    if target_etf and current_shares == 0:
        # 目标ETF不在持仓中，买入
        actual_buy = min(strategy_capital, cash)

        if actual_buy < 100:
            log.warning("    [%s] 资金不足，跳过买入（现金=%.2f）" % (target_etf, cash))
            log.info("=" * 60)
            return

        # 获取实时价格
        price = data[target_etf].price if hasattr(data[target_etf], 'price') else 0

        if price <= 0:
            # 判断失败原因：区分"未开盘"和"停牌/数据异常"
            current_time = context.blotter.current_dt.strftime('%H:%M')
            is_cross_border = target_etf in g.cross_border_etfs  # 是否跨境ETF

            if is_cross_border and current_time < '10:30':
                # 跨境ETF未开盘（10:30才开盘）
                log.warning("    [%s] 无法获取价格（跨境ETF未开盘，等待10:30二次尝试）" % target_etf)
                g.buy_order_failed = True  # 设置失败标志，触发10:30二次尝试
            else:
                # 普通ETF或10:30之后仍无法获取价格 → 停牌/数据异常
                log.warning("    [%s] 无法获取价格（停牌或数据异常，不触发10:30二次尝试）" % target_etf)
                g.buy_order_failed = False  # 不触发10:30二次尝试
                # 9:31-35重试机制会继续尝试（最多4次）
            log.info("=" * 60)
            return

        log.info("    [%s] 实时价=%.3f | 目标买入=%.2f元（满仓）"
                 % (target_etf, price, actual_buy))

        # 拆单买入（单笔最大金额 = 90万股 × 价格 × 0.95）
        max_value = 900000 * price * 0.95
        remaining = actual_buy
        order_count = 0

        while remaining > 0:
            batch = min(remaining, max_value)
            if batch > 0:
                order_value(target_etf, batch)
                order_count += 1
                remaining -= batch
            else:
                break

        # 注意：买入后不立即更新owned_positions，等待重试检查确认实际成交
        # 记录下单信息，供重试检查使用
        g.buy_order_value = actual_buy
        g.buy_order_count = order_count
        g.buy_order_price = price

        log.info("    [%s] 买入下单 → 下单%d笔，共%.2f元，等待成交确认"
                 % (target_etf, order_count, actual_buy))

    elif target_etf:
        log.info("    [%s] 已持有%d股，无需买入" % (target_etf, current_shares))
    else:
        log.info("    无目标ETF，空仓观望")

    log.info("=" * 60)


# ============ 盘后处理 ============
def after_trading_end(context, data):
    """盘后同步+持久化"""

    # ========== 盘后强制同步持仓（v1.5.1新增）==========
    # 解决：盘中买入成交确认遗漏的问题
    # 如果有下单记录但未确认成交，强制从账户同步持仓
    buy_order_value = getattr(g, 'buy_order_value', 0)
    if buy_order_value > 0 and g.target_etf:
        # 有下单记录，检查账户真实持仓
        real_pos = context.portfolio.positions.get(g.target_etf)
        actual_shares = real_pos.amount if real_pos else 0

        if actual_shares > 0:
            # 有实际持仓，强制更新owned_positions
            g.owned_positions[g.target_etf] = actual_shares
            log.info("[盘后强制同步] [%s] 发现实际持仓%d股，强制更新owned_positions"
                     % (g.target_etf, actual_shares))
            # 清除下单记录
            g.buy_order_value = 0
            g.buy_order_price = 0
            g.buy_order_failed = False
        else:
            log.warning("[盘后强制同步] [%s] 下单%.2f元但实际持仓为0，可能订单失败"
                        % (g.target_etf, buy_order_value))

    # ========== 盘后强制同步卖出持仓（v1.5.2新增）==========
    sell_orders = getattr(g, 'sell_orders', [])
    if sell_orders:
        log.info("-" * 60)
        log.info("[盘后卖出同步] 发现%d只待确认卖出订单" % len(sell_orders))

        sell_confirmed = []  # 已成交的卖出订单
        for order in sell_orders[:]:  # 遍历副本
            etf = order['etf']
            expected_shares = order['shares']

            # 检查实际持仓
            real_pos = context.portfolio.positions.get(etf)
            actual_shares = real_pos.amount if real_pos else 0

            if actual_shares == 0:
                # 已成交清仓
                sell_confirmed.append(etf)
                if etf in g.owned_positions:
                    del g.owned_positions[etf]
                log.info("[盘后卖出同步] [%s] 已清仓，删除owned_positions" % etf)
            else:
                # 未成交或部分成交
                log.warning("[盘后卖出同步] [%s] 未清仓，实际持仓=%d股（预期清仓%d股）"
                            % (etf, actual_shares, expected_shares))

                # 强制同步owned_positions为实际持仓
                if actual_shares > 0:
                    g.owned_positions[etf] = actual_shares
                    log.info("[盘后卖出同步] [%s] 强制更新owned_positions=%d股"
                             % (etf, actual_shares))
                else:
                    # 实际持仓为0，删除owned_positions
                    if etf in g.owned_positions:
                        del g.owned_positions[etf]
                    log.info("[盘后卖出同步] [%s] 实际持仓为0，删除owned_positions" % etf)

                sell_confirmed.append(etf)  # 标记为已处理

        # 清空卖出订单列表
        for etf in sell_confirmed:
            g.sell_orders = [o for o in g.sell_orders if o['etf'] != etf]

        log.info("[盘后卖出同步] 处理完成，剩余待确认订单: %d只" % len(g.sell_orders))

        # 强制清空卖出订单列表（盘后强制清空）
        if g.sell_orders:
            log.warning("[盘后卖出同步] 强制清空未确认订单: %d只" % len(g.sell_orders))
            g.sell_orders = []

    # 盘前同步持仓
    _sync_owned_positions(context)

    # 仅实盘保存状态
    if is_trade():
        _save_state(context)
        log.info("[盘后] 实盘持久化完成")
    else:
        log.info("[盘后] 回测模式，不持久化")

    # ========== 盘后汇总 ==========
    total_value = context.portfolio.total_value
    cash = context.portfolio.cash
    positions_value = total_value - cash
    strategy_capital = total_value * g.capital_ratio

    owned_list = list(g.owned_positions.keys())

    log.info("=" * 60)
    log.info("【盘后汇总】日期: %s" % g.current_date)
    log.info("-" * 60)
    log.info(">>> 资金状况")
    log.info("    总资产: %.2f元" % total_value)
    log.info("    现金: %.2f元" % cash)
    log.info("    持仓市值: %.2f元" % positions_value)
    log.info("    策略可用资金: %.2f元 (比例=%.0f%%)"
             % (strategy_capital, g.capital_ratio * 100))

    log.info("-" * 60)
    log.info(">>> 本策略持仓: %d只" % len(owned_list))
    for etf in owned_list:
        amount = g.owned_positions.get(etf, 0)
        try:
            price = data[etf].price if hasattr(data[etf], 'price') else 0
            value = amount * price if amount > 0 else 0
            log.info("    [%s] %d股 | 市值=%.2f元 | 价格=%.3f"
                     % (etf, amount, value, price))
        except:
            log.info("    [%s] %d股" % (etf, amount))

    if not owned_list:
        log.info("    (空仓)")

    # ========== 账户真实持仓显示（v1.5.1新增）==========
    # 解决：owned_positions可能遗漏的问题，显示账户真实持仓作为对照
    log.info("-" * 60)
    log.info(">>> 账户真实持仓对照:")
    account_positions = []
    for code, pos in context.portfolio.positions.items():
        amount = getattr(pos, 'amount', 0)
        if amount > 0:
            account_positions.append(code)
            try:
                price = data[code].price if hasattr(data[code], 'price') else 0
                value = amount * price if amount > 0 else 0
                # 检查是否在ETF池内
                in_pool = code in g.etf_pool
                pool_mark = "✓池内" if in_pool else "✗池外"
                log.info("    [%s] %d股 | 市值=%.2f元 | %s"
                         % (code, amount, value, pool_mark))
            except:
                log.info("    [%s] %d股" % (code, amount))

    if not account_positions:
        log.info("    (空仓)")

    # 如果账户持仓与策略持仓不一致，警告
    if len(account_positions) != len(owned_list):
        log.warning("[持仓对照] 账户有%d只，策略追踪%d只，不一致！请检查持久化"
                    % (len(account_positions), len(owned_list)))

    log.info("=" * 60)