# ETF核心资产轮动策略（安全摸狗策略）v1.4 - PTrade版本
# ==============================
#
# 【策略概述】
# 每日选择动量得分最高的1只ETF满仓持有，追求简单高效
#
# 【交易规则】
# - 盘前选股：09:00前完成动量计算，确定目标ETF
# - 开盘调仓：09:30开盘即执行买卖（使用盘前选股结果）
# - 重试机制：09:31-35每分钟检查，未成交则重试（最多4次）
# - 持仓数量：仅1只（动量得分最高且在安全区间内）
# - 动量计算：加权线性回归（25天，近期权重更大）
# - 打分公式：年化收益 × R²
# - 安全区过滤：score > 0 且 <= 5（避免追高风险）
# - 资金上限：g.capital_ratio 控制策略可用资金比例
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
#    - PTrade：盘前选股 + handle_data开盘交易 + 重试机制
#
# ==================== 文件信息 ====================
#
# 版本：v1.4（多策略持仓校验模块集成）
# 更新日期：2026-05-27
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
    # ===== 0. 策略信息声明（多策略校验模块使用）=====
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

    # ===== 5. 检查账户持仓状态（仅记录日志，不同步）=====
    _check_account_positions(context)

    # ===== 6. ETF池 =====
    g.etf_pool = [
        '518880.SS',   # 黄金ETF（大宗商品）
        '513100.SS',   # 纳指100（海外资产）
        '159915.SZ',   # 创业板100（成长股、科技股、中小盘）
        '510180.SS',   # 上证180（价值股、蓝筹股、中大盘）
    ]
    g.pool_config['value'] = g.etf_pool  # 更新股票池配置

    # ===== 6. 全局持仓校验（多策略并行时使用）=====
    if is_trade():
        try:
            from shared_position_validator import validate_strategy_positions
            g.owned_positions = validate_strategy_positions(
                context,
                g.strategy_name,
                g.pool_config,
                g.owned_positions,
                get_research_path_func=get_research_path,
                log_func=log.info,
                is_trade_func=is_trade
            )
            # 保存校验后的合法持仓
            _save_state(context)
        except Exception as e:
            log.warning('[校验] 校验模块调用失败: %s，使用原始持仓' % str(e))

    # ===== 7. 检查账户持仓状态（仅记录日志，不同步）=====
    _check_account_positions(context)

    # 设置股票池
    set_universe(g.etf_pool)

    # 设置基准
    set_benchmark('000300.XSHG')

    # ===== 8. 策略参数 =====
    g.m_days = 25  # 动量参考天数
    g.capital_ratio = 1.0  # 策略可用资金比例

    log.info("=" * 60)
    log.info("【策略初始化】")
    log.info("-" * 60)
    log.info("    ETF池: %s" % ','.join(g.etf_pool))
    log.info("    动量天数: %d" % g.m_days)
    log.info("    持仓数量: 1只（动量最高）")
    log.info("    安全区: score > 0 且 <= 5")
    log.info("    资金比例: %.0f%%" % (g.capital_ratio * 100))
    log.info("=" * 60)

    # ===== 9. 调仓控制 =====
    g.trade_done_today = False
    g.current_date = ''

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
    g.retry_count = 0      # 重试次数计数器
    g.target_etf = None    # 目标ETF（用于重试检查）
    g.trade_flag = True    # 允许交易（开盘后第一次handle_data即执行）

    # 盘前同步持仓
    _sync_owned_positions(context)

    # ========== 盘前选股（提前计算，开盘直接交易）==========
    log.info("=" * 60)
    log.info("【盘前选股】日期: %s | 时间: 09:00前" % g.current_date)
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

    current_time = context.blotter.current_dt.strftime('%H:%M')

    # 第一次调仓（开盘后第一次handle_data调用）
    if g.trade_flag and not g.trade_done_today:
        log.info("=" * 60)
        log.info("【每日调仓】日期: %s | 时间: %s | 第一次调用" % (g.current_date, current_time))
        log.info("=" * 60)

        trade(context, data)
        g.trade_done_today = True
        g.trade_flag = False  # 关闭交易flag，防止重复执行
        g.retry_count = 0     # 初始化重试计数器

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


def check_and_retry(context, data):
    """检查调仓是否完成，未完成则重试"""
    need_retry = False

    # ========== 1. 检查卖出是否完成 ==========
    hold_list = [etf for etf in g.owned_positions if _get_owned_amount(etf, context) > 0]

    # 应该清仓但还持有的ETF（不在目标池）
    sell_pending = []
    for etf in hold_list:
        if etf != g.target_etf:
            owned_enable = _get_owned_enable_amount(etf, context)
            if owned_enable > 0:
                sell_pending.append(etf)
                need_retry = True

    if sell_pending:
        log.info("-" * 60)
        log.info("[重试检查] 发现待卖出ETF: %s" % ','.join(sell_pending))
        for etf in sell_pending:
            owned_enable = _get_owned_enable_amount(etf, context)
            if owned_enable > 0:
                # 拆单卖出
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
                log.info("[重试] [%s] 卖出%d股" % (etf, owned_enable))
                if etf in g.owned_positions:
                    del g.owned_positions[etf]

    # ========== 2. 检查买入是否完成 ==========
    if g.target_etf:
        current_shares = _get_owned_amount(g.target_etf, context)

        # 获取实时价格
        try:
            price = data[g.target_etf].price if hasattr(data[g.target_etf], 'price') else 0
        except:
            price = 0

        if price > 0 and current_shares == 0:
            # 目标ETF未买入成功，重试买入
            need_retry = True

            # 重新获取资金状况
            total_value = context.portfolio.total_value
            cash = context.portfolio.cash
            strategy_capital = total_value * g.capital_ratio
            actual_buy = min(strategy_capital, cash)

            if actual_buy >= 100:
                log.info("-" * 60)
                log.info("[重试检查] 目标ETF [%s] 未买入成功，重试买入" % g.target_etf)
                log.info("    当前现金=%.2f元, 策略可用=%.2f元" % (cash, strategy_capital))

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

                # 更新owned_positions（估算买入股数）
                estimated_shares = int(actual_buy / price / 100) * 100
                g.owned_positions[g.target_etf] = estimated_shares

                log.info("[重试] [%s] 下单%d笔，共%.2f元，估算%d股"
                         % (g.target_etf, order_count, actual_buy, estimated_shares))

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

                try:
                    price = data[etf].price if hasattr(data[etf], 'price') else 0
                    sell_value = owned_enable * price
                    log.info("    [%s] 卖出 → 清仓%d股，市值%.2f元"
                             % (etf, owned_enable, sell_value))
                except:
                    log.info("    [%s] 卖出 → 清仓%d股" % (etf, owned_enable))

                # 更新owned_positions
                if etf in g.owned_positions:
                    del g.owned_positions[etf]
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
            log.warning("    [%s] 无法获取价格，跳过买入" % target_etf)
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

        # 更新owned_positions（估算买入股数）
        estimated_shares = int(actual_buy / price / 100) * 100
        g.owned_positions[target_etf] = estimated_shares

        log.info("    [%s] 买入完成 → 下单%d笔，共%.2f元，估算%d股"
                 % (target_etf, order_count, actual_buy, estimated_shares))

    elif target_etf:
        log.info("    [%s] 已持有%d股，无需买入" % (target_etf, current_shares))
    else:
        log.info("    无目标ETF，空仓观望")

    log.info("=" * 60)


# ============ 盘后处理 ============
def after_trading_end(context, data):
    """盘后同步+持久化"""
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

    log.info("=" * 60)