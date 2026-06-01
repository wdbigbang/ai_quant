# -*- coding: utf-8 -*-
# 多策略控制器 v3.1 - PTrade版本（修复ETF持仓干扰问题）
#
# 【v3.1修复】(2026-05-13)
# - 修复ETF持仓干扰小市值冷静期判断的问题
# - _get_strategy_assets_small_cap: 排除ETF持仓，避免策略资产计算混淆
# - _log_strategy_capital_status: 排除其他策略持仓，修正盘前状态日志
# - 根因：当ETF和小市值并行运行时，ETF持仓被算入小市值策略资产
#
# 【v3.0修改】(2026-05-13)
# - 移除小市值补买逻辑：补买导致超跌和更大亏损
# - 简化买入逻辑：只买入新股票，不再补买现有持仓
# - 盘前份额重置保留（v2.9修复）
#
# 【v2.9修复】(2026-05-13)
# - 盘前份额重置：g.strategy_used动态更新为虚拟持仓市值
# - 解决第二天无法补买问题（第一天用完份额后第二天remaining=0）
# - 核心逻辑：remaining = quota - used = quota - 持仓市值
#
# 【v2.8修复】(2026-05-13)
# - 买入顺序调整：小市值先买（波动大），ETF后买（波动小）
# - 份额检查修复：改为<=，允许remaining==value时买入
# - 虚拟持仓估算修复：买入刚好1手时也记录虚拟持仓
#
# 【v2.7修复】(2026-05-12)
# - buy_etfs函数改用固定份额机制（之前仍用动态资产计算）
# - 目标金额基于固定份额quota，买入前刷新剩余份额检查
# - 解决第一天ETF只买一只的bug
#
# 【v2.6固定份额方案】(2026-05-12)
# - 每个策略分配固定份额 = 初始资金 × 资金比例（不随总现金变化）
# - safe_buy_value检查剩余份额，safe_sell回收份额
# - 解决并行模式资金分配问题
#
# 【v2.3新增】(2026-05-11)
# - 启动时持仓对齐：盘中启动时检查已有持仓归属，不属于任何启用策略则卖出
# - ETF选股提前到盘前：确保启动对齐时ETF选股结果已准备好
# - T+1受限处理：无法卖出的持仓记录到待卖出列表，第二天执行卖出
# - 只检查启用的策略：资金比例>0的策略才参与归属判断
#
# 【v2.2修复】(2026-05-08)
# - 盘前同步修复：只同步本策略已有持仓，避免50%+50%并行时持仓混淆
# - 卖出拆单修复：所有卖出场景自动拆单（单笔最大90万股）
#
# 【v2.0核心机制】
# - 固定份额追踪：策略份额 = 初始资金 × 资金比例（不随总现金变化）
# - 买入检查剩余份额，卖出回收份额，防止并行超买
# - 虚拟持仓追踪：记录每个策略的持仓股数（用于防止超卖）
#
# 【时间调度规则】[v2.8调整：小市值买入优先于ETF]
# 优先级从高到低：
# 1. 启动时持仓对齐（生命周期内首次handle_data，优先级最高）
# 2. 14:49 → 小市值卖出
# 3. 10:30/13:30/14:30 → 小市值冷静期检查
# 4. 每日首次handle_data → 处理待卖出股票（T+1受限）
# 5. 小市值买入（09:30-14:40，当天只执行一次）[v2.8：优先买入]
# 6. ETF月初调仓（<14:40，分两分钟：先卖后买）
# 7. 其他时间 → 分钟止盈
#
# ==============================

import numpy as np
import pandas as pd
import math
from scipy.linalg import solve
from datetime import datetime, timedelta


# ============================================================
#                    初始化函数
# ============================================================

def initialize(context):
    """
    策略初始化 - 注册双策略（固定份额追踪）

    【v2.6固定份额机制】
    - 每个策略分配固定份额 = 初始资金 × 资金比例
    - 买入检查剩余份额，卖出回收份额
    - 解决并行模式资金分配问题

    【资金比例设置】
    - ETF 50%, 小市值 50%（并行测试模式）
    """
    log.info("=" * 70)
    log.info("=== 多策略控制器 v2.8 初始化（修复买入顺序+份额检查）===")

    set_benchmark("000300.XSHG")

    # ==================== 策略资金比例（并行模式）====================
    # v2.3：50%+50%并行测试模式
    g.capital_ratio_small_cap = 0.5  # 小市值策略50%
    g.capital_ratio_etf = 0.5        # ETF策略50%

    log.info("[资金比例] 小市值: %.0f%%，ETF: %.0f%%"
             % (g.capital_ratio_small_cap * 100, g.capital_ratio_etf * 100))
    log.info("[v2.6机制] 固定份额追踪：份额 = 初始资金 × 比例（不随总现金变化）")
    log.info("[v2.2修复] 盘前同步只同步本策略已有持仓，避免混淆")

    # ==================== [v2.6新增] 固定份额追踪 ====================
    # 解决并行模式问题：ETF先买后小市值份额不足
    # 每个策略分配固定份额，买入检查剩余份额，卖出回收份额
    g.initial_capital = context.portfolio.starting_cash
    g.strategy_quota = {
        'small_cap': g.initial_capital * g.capital_ratio_small_cap,
        'etf_rotation': g.initial_capital * g.capital_ratio_etf
    }
    g.strategy_used = {
        'small_cap': 0,
        'etf_rotation': 0
    }
    log.info("[固定份额] 初始资金%.0f, 小市值%.0f, ETF%.0f"
             % (g.initial_capital, g.strategy_quota['small_cap'], g.strategy_quota['etf_rotation']))

    # ==================== 策略注册表（仅保留虚拟持仓追踪）====================
    g.strategies = {
        'small_cap': {
            'positions': {},  # 虚拟持仓（用于防止超卖）
        },
        'etf_rotation': {
            'positions': {},  # 虚拟持仓（用于防止超卖）
        }
    }

    log.info("[策略注册] 小市值虚拟持仓追踪启用, ETF虚拟持仓追踪启用")

    # ==================== 小市值策略参数 ====================
    # 基础参数
    g.index_small_cap = "399101.XBHS"          # 深证100指数（小市值股票池）
    g.buy_stock_count_small_cap = 7            # 持仓数量（分散持仓，降低单股风险）
    g.screen_stock_count_small_cap = 15        # 筛选数量（买入候选池）
    g.down_stock_count_small_cap = 15          # 卖出候选数量

    # ROE筛选参数
    g.roe_filter_small_cap = True              # 启用ROE筛选（盈利能力过滤）
    g.roe_threshold_small_cap = 0              # ROE阈值（单季度ROE>0）
    g.roe_improve_filter_small_cap = True      # 启用ROE改善筛选（成长性过滤）
    g.roe_improve_top_small_cap = 0.3          # ROE改善前30%（4倍当季-前4季平均）

    # 止盈止损参数
    g.uprate_small_cap = 8.0                   # 止盈阈值：涨幅≥8%时卖出
    g.downrate_small_cap = None                # 回补阈值：关闭（避免频繁交易）
    g.sell_cooldown_days_small_cap = 5         # 卖出后冷却期（防止追涨杀跌）
    g.sold_stocks_dates_small_cap = {}         # 卖出日期记录 {股票代码: 日期}

    # 冷静期参数（组合跌幅风控）
    g.cooldown_days_small_cap = 5              # 冷静期天数（组合跌幅触发后空仓5天）
    g.decline_days_small_cap = 3               # 连续下跌天数（连续3天跌幅≥阈值触发）
    g.decline_threshold_small_cap = -0.02      # 单日跌幅阈值（-2%）
    g.empty_months_small_cap = [4]             # 空仓月份（4月年报披露期，规避风险）
    g.money_fund_small_cap = "511880.SS"       # 货币基金：银华日利（冷静期/空仓月避险）

    # 状态变量（运行时更新）
    g.in_cooldown_small_cap = False            # 是否处于冷静期
    g.last_sell_date_small_cap = None          # 上次卖出日期
    g.days_since_sell_small_cap = 0            # 距离上次卖出天数
    g.cooldown_count_small_cap = 0             # 冷静期触发次数（统计）
    g.cooldown_dates_small_cap = []            # 冷静期触发日期列表（统计）
    g.portfolio_values_small_cap = []          # 组合市值历史（用于跌幅检查）

    # 当日交易记录
    g.today_bought_stocks_small_cap = set()    # 当日买入股票集合（防止重复买入）
    g.today_sold_stocks_small_cap = set()      # 当日卖出股票集合（防止重复卖出）

    # 选股数据缓存
    g.df2_small_cap = None                     # 市值数据DataFrame（盘前选股结果）
    g.current_date_small_cap = None            # 当前日期（盘前选股基准日期）
    g.handle_data_flag_small_cap = False       # handle_data启用标志

    # 价格数据缓存
    g.yesterday_close_small_cap = {}           # 昨日收盘价（用于涨幅计算）

    # 触发标志（盘前检查结果）
    g.trigger_cooldown_small_cap = False       # 触发冷静期清仓
    g.trigger_empty_month_small_cap = False    # 触发空仓月清仓
    g.empty_month_clear_done = False           # 空仓月清仓已执行标志
    g.buy_done_today_small_cap = False         # 当天买入已完成标志
    g.first_handle_data_done_small_cap = False # 当天首次handle_data已执行标志

    # ==================== 启动时持仓对齐（v2.3新增）====================
    g.first_start_done = False                # 生命周期标志：启动对齐已执行（策略生命周期内只执行一次）
    g.pending_sell_stocks = {}                # 待卖出股票 {代码: {'amount': 100}}（T+1受限）
    g.first_handle_data_done_global = False   # 全局首次handle_data标志（用于处理待卖出）

    if g.capital_ratio_small_cap > 0:
        log.info("[小市值] 指数: %s, 持仓数: %d, 止盈: %.1f%%"
                 % (g.index_small_cap, g.buy_stock_count_small_cap, g.uprate_small_cap))

    # ==================== ETF轮动策略参数 ====================
    # ETF池（13只宽基+行业ETF，覆盖主要资产类别）
    g.etf_pool = [
        # 商品/外汇（避险资产）
        '518880.SS',    # 黄金ETF
        '159985.SZ',    # 豆粕ETF（农产品）
        '513100.SS',    # 纳斯达克100（美股）
        # 宽基指数（核心仓位）
        '510300.SS',    # 沪深300（大盘蓝筹）
        '159915.SZ',    # 创业板100（成长股）
        # 行业ETF（卫星仓位）
        '159992.SZ',    # 创新药
        '515700.SS',    # 新能源汽车
        '510150.SS',    # 红利指数（价值股）
        '515790.SS',    # 稀土ETF（资源股）
        '515880.SS',    # 通信设备（科技股）
        '512720.SS',    # 半导体（芯片）
        '512660.SS',    # 军工ETF
        '159740.SZ',    # 消费ETF
    ]

    # EPO优化参数（Enhanced Portfolio Optimization）
    g.stock_num_etf = 3                        # 持仓ETF数量（分散持仓）
    g.m_days_etf = 34                          # 动量计算天数（34日动量因子）
    g._lambda_etf = 10                         # 风险厌恶系数（越大越保守）
    g.w_etf = 0.2                              # 收缩权重（协方差矩阵收缩强度）

    # ETF调仓控制
    g.last_trade_month_etf = -1                # 上次调仓月份（月初调仓控制）
    g.trade_done_today_etf = False             # 当天调仓已完成标志
    g.sell_done_etf = False                    # ETF卖出已完成标志（分两分钟执行）
    g.buy_done_etf = False                     # ETF买入已完成标志

    # ETF目标持仓缓存
    g.target_etfs = []                         # 目标ETF列表（EPO优化结果）
    g.target_weights = []                      # 目标权重数组（EPO优化结果）
    g.etf_weight_map = {}                      # ETF权重字典 {ETF代码: 权重}

    # ETF价格数据缓存
    g.fq_factor_etf = {}                       # 复权因子 {ETF代码: 因子}（用于前复权价格）
    g.yesterday_close_etf = {}                 # 昨日收盘价（用于涨停判断）

    if g.capital_ratio_etf > 0:
        log.info("[ETF] 持仓数: %d, 动量天数: %d" % (g.stock_num_etf, g.m_days_etf))

    # ==================== 统一股票池订阅 ====================
    set_universe(g.etf_pool)

    # ==================== 回测设置 ====================
    if not is_trade():
        set_backtest()

    log.info("=" * 70)


def set_backtest():
    """回测设置"""
    set_limit_mode("UNLIMITED")
    set_commission(commission_ratio=0.0003, min_commission=5.0)
    set_slippage(slippage=0.002)


# ============================================================
#                    安全下单函数（策略隔离核心）
# ============================================================

def _get_latest_price(security):
    """
    获取当前最新价（通过get_history获取最近收盘价）

    注：避免读取未闭合K线造成未来信息
    """
    try:
        df = get_history(2, '1d', 'close', security_list=security, fq=None, include=False)
        if df is None or df.empty:
            log.error('[价格] 获取 %s 失败' % security)
            return None
        return float(df['close'].iloc[-1])
    except Exception as e:
        log.error('[价格] %s 异常: %s' % (security, str(e)))
        return None


def safe_buy(context, strategy_name, security, amount, limit_price=None):
    """
    子策略安全买入（按比例动态隔离）

    【资金隔离机制 - v2.0修复】
    1. 动态计算策略可用资金（总现金 × 资金比例）
    2. 检查策略可用资金是否充足（防止策略超支）
    3. 检查真实账户资金是否充足（防止真实超支）
    4. 下单成功后更新虚拟持仓

    【参数】
    - context: 策略上下文（必须传入）
    - strategy_name: 子策略名称（'small_cap' 或 'etf_rotation'）
    - security: 标的代码
    - amount: 期望买入股数（自动取整到100股）
    - limit_price: 限价，None表示使用最新价

    【返回】
    - order_id 或 None
    """
    if strategy_name not in g.strategies:
        log.error('[safe_buy] 未知策略 %s' % strategy_name)
        return None

    # [修复] 动态获取资金比例
    capital_ratio = _get_capital_ratio(strategy_name)
    if capital_ratio <= 0:
        return None

    # 取整到100股
    amount = int(amount / 100) * 100
    if amount <= 0:
        log.warning('[%s] safe_buy: 买入数量不足100股，跳过' % strategy_name)
        return None

    # 确定委托价格
    price = limit_price
    if price is None:
        price = _get_latest_price(security)
        if price is None:
            return None

    # 估算所需资金（含1‰缓冲，避免因滑点不足）
    estimated_cost = price * amount * 1.001

    # [修复] 动态计算策略可用资金（总现金 × 资金比例）
    real_cash = context.portfolio.cash
    strategy_cash = real_cash * capital_ratio

    if strategy_cash < estimated_cost:
        log.warning('[%s] safe_buy: 策略可用资金不足，需要%.2f，策略可用%.2f（总现金%.2f × %.0f%%）'
                    % (strategy_name, estimated_cost, strategy_cash, real_cash, capital_ratio * 100))
        return None

    # 检查真实账户资金是否充足
    if real_cash < estimated_cost:
        log.warning('[%s] safe_buy: 真实账户资金不足，需要%.2f，真实剩余%.2f'
                    % (strategy_name, estimated_cost, real_cash))
        return None

    # 真实下单
    order_id = order(security, amount, limit_price=limit_price)

    if order_id is None:
        log.error('[%s] safe_buy: 下单失败' % strategy_name)
        return None

    # 更新虚拟持仓（用于卖出检查）
    strat = g.strategies[strategy_name]
    old_virtual = strat['positions'].get(security, 0)
    strat['positions'][security] = old_virtual + amount

    # [DEBUG] 记录虚拟持仓更新
    log.info('[DEBUG][%s] safe_buy更新虚拟持仓: %s %d -> %d (买入%d股)'
             % (strategy_name, security, old_virtual, strat['positions'][security], amount))

    log.info('[%s] safe_buy成功: %s x %d股，委托价%.3f，策略可用资金%.2f'
             % (strategy_name, security, amount, price, strategy_cash))
    return order_id


def _get_capital_ratio(strategy_name):
    """
    获取策略资金比例

    【参数】
    - strategy_name: 'small_cap' 或 'etf_rotation'

    【返回】
    - 资金比例（0.0-1.0）
    """
    if strategy_name == 'small_cap':
        return g.capital_ratio_small_cap
    elif strategy_name == 'etf_rotation':
        return g.capital_ratio_etf
    else:
        log.error('[资金比例] 未知策略 %s' % strategy_name)
        return 0.0


def safe_sell(context, strategy_name, security, amount, limit_price=None):
    """
    子策略安全卖出（按比例动态隔离）

    【持仓隔离机制 - v2.0修复】
    1. 检查策略虚拟持仓是否充足（防止策略超卖）
    2. 检查真实持仓可用数量（防止真实超卖）
    3. 取min(真实可用, 虚拟持仓)避免超卖
    4. 下单成功后更新虚拟持仓

    【参数】
    - context: 策略上下文（必须传入）
    - strategy_name: 子策略名称
    - security: 标的代码
    - amount: 期望卖出股数；None表示清空该策略虚拟持仓
    - limit_price: 限价，None表示使用最新价

    【返回】
    - order_id 或 None
    """
    if strategy_name not in g.strategies:
        log.error('[safe_sell] 未知策略 %s' % strategy_name)
        return None

    # [修复] 动态获取资金比例
    capital_ratio = _get_capital_ratio(strategy_name)
    if capital_ratio <= 0:
        return None

    strat = g.strategies[strategy_name]

    # 该策略的虚拟持仓
    virtual_amount = strat['positions'].get(security, 0)

    # [DEBUG] 获取真实持仓并对比
    try:
        real_position = get_position(security)
        real_amount = real_position.amount if real_position else 0
        real_enable = real_position.enable_amount if real_position and hasattr(real_position, 'enable_amount') else 0
    except:
        real_amount = 0
        real_enable = 0

    # [DEBUG] 记录持仓差异
    if virtual_amount != real_amount:
        log.info('[DEBUG][持仓差异][%s] %s: 虚拟持仓=%d, 真实持仓=%d, 可卖=%d'
                 % (strategy_name, security, virtual_amount, real_amount, real_enable))

    if virtual_amount <= 0:
        log.warning('[%s] safe_sell: 该策略无%s虚拟持仓（虚拟=%d, 真实=%d），跳过'
                    % (strategy_name, security, virtual_amount, real_amount))
        return None

    # 确定期望卖出数量
    if amount is None:
        amount = virtual_amount
    amount = int(amount / 100) * 100
    if amount <= 0:
        log.warning('[%s] safe_sell: 卖出数量不足100股，跳过' % strategy_name)
        return None

    # 不超过本策略虚拟持仓
    amount = min(amount, virtual_amount)

    # 获取真实持仓数量（可用数量）
    try:
        real_position = get_position(security)
        real_enable = real_position.enable_amount if real_position and hasattr(real_position, 'enable_amount') else 0
    except:
        real_enable = 0

    # 取min(真实可用, 虚拟持仓)避免超卖
    safe_amount = min(amount, real_enable)
    safe_amount = int(safe_amount / 100) * 100

    if safe_amount <= 0:
        log.warning('[%s] safe_sell: 真实可用持仓不足（真实可用=%d，虚拟=%d），跳过'
                    % (strategy_name, real_enable, virtual_amount))
        return None

    # ==================== 拆单卖出 ====================
    # 单笔最大90万股，避免大单冲击市场
    remaining = safe_amount
    order_ids = []
    total_sold = 0

    while remaining > 0:
        batch = min(remaining, 900000)  # 单笔最大90万股
        batch = int(batch / 100) * 100  # 向下取整到100股

        if batch > 0:
            # 真实下单（卖出为负数）
            order_id = order(security, -batch, limit_price=limit_price)
            if order_id is not None:
                order_ids.append(order_id)
                total_sold += batch
            remaining -= batch
        else:
            # 剩余不足100股，一次性卖出
            if remaining > 0:
                order_id = order(security, -remaining, limit_price=limit_price)
                if order_id is not None:
                    order_ids.append(order_id)
                    total_sold += remaining
            break

    if total_sold <= 0:
        log.error('[%s] safe_sell: 拆单卖出失败' % strategy_name)
        return None

    # 更新虚拟持仓
    old_virtual = virtual_amount
    strat['positions'][security] = virtual_amount - total_sold
    if strat['positions'][security] <= 0:
        del strat['positions'][security]

    # [v2.6] 回收份额：计算卖出金额并减少已使用份额
    price = limit_price
    if price is None:
        price = _get_latest_price(security)
    if price and price > 0:
        sold_value = total_sold * price
        old_used = g.strategy_used.get(strategy_name, 0)
        g.strategy_used[strategy_name] = max(0, old_used - sold_value)
        log.info('[DEBUG][%s] 份额回收: %.2f元，已用%.2f -> %.2f'
                 % (strategy_name, sold_value, old_used, g.strategy_used[strategy_name]))

    # [DEBUG] 记录虚拟持仓更新
    new_virtual = strat['positions'].get(security, 0)
    log.info('[DEBUG][%s] safe_sell拆单成功: %s 卖出%d股（拆%d笔），虚拟持仓 %d -> %d'
             % (strategy_name, security, total_sold, len(order_ids), old_virtual, new_virtual))

    log.info('[%s] safe_sell成功: %s x %d股（拆单%d笔），虚拟剩余持仓%d'
             % (strategy_name, security, total_sold, len(order_ids), new_virtual))
    return order_id


def safe_buy_value(context, strategy_name, security, value, limit_price=None):
    """
    按金额买入（固定份额追踪模式）

    【资金隔离机制 - v2.6固定份额方案】
    1. 每个策略分配固定份额 = 初始资金 × 资金比例（不随总现金变化）
    2. 买入检查剩余份额（quota - used >= value）
    3. 买入成功后更新已使用资金（used += value）
    4. 卖出时回收份额（used -= sold_value）

    【解决并行模式问题】
    - ETF和小市值各分配固定份额，不互相侵占
    - 即使ETF先买入消耗总现金，小市值份额仍然充足

    【参数】
    - context: 策略上下文（必须传入）
    - strategy_name: 子策略名称
    - security: 标的代码
    - value: 目标买入金额
    - limit_price: 限价

    【返回】
    - order_id 或 None
    """
    if strategy_name not in g.strategies:
        return None

    # [v2.6] 固定份额检查 [v2.8修复：改为<=，允许刚好等于时买入]
    quota = g.strategy_quota.get(strategy_name, 0)
    used = g.strategy_used.get(strategy_name, 0)
    remaining = quota - used

    if remaining < value and abs(remaining - value) > 0.01:  # [v2.8] 允许误差范围内的相等
        log.warning('[%s] safe_buy_value: 策略份额不足%.2f，剩余份额%.2f（总额%.2f - 已用%.2f）'
                    % (strategy_name, value, remaining, quota, used))
        return None

    if value <= 0:
        return None

    # 检查真实资金（仍然需要确保有足够现金）
    real_cash = context.portfolio.cash
    if real_cash < value:
        log.warning('[%s] safe_buy_value: 真实资金不足%.2f，真实剩余%.2f'
                    % (strategy_name, value, real_cash))
        return None

    # 真实下单（order_value按金额买入）
    try:
        order_id = order_value(security, value, limit_price=limit_price)
    except Exception as e:
        log.error('[%s] safe_buy_value: %s 下单异常 %s' % (strategy_name, security, str(e)))
        return None

    if order_id is None:
        log.error('[%s] safe_buy_value: 下单失败' % strategy_name)
        return None

    # [v2.6] 更新已使用份额
    g.strategy_used[strategy_name] = used + value
    log.info('[DEBUG][%s] 份额使用: %.2f元，累计已用%.2f，剩余份额%.2f'
             % (strategy_name, value, g.strategy_used[strategy_name], remaining - value))

    # [v2.6] 使用保守估算，确保虚拟持仓<=真实持仓
    # 盘后同步会修正差额
    # [v2.8修复] 买入刚好1手时也记录虚拟持仓（不再减100股）
    strat = g.strategies[strategy_name]
    price = limit_price
    if price is None:
        price = _get_latest_price(security)
    if price and price > 0:
        # [v2.8修改] 向下取整到100股，但不再减100股作为缓冲
        # 原问题：买入3571元刚好1手时，estimated_shares=0，虚拟持仓不记录
        estimated_shares = int(value / price / 100) * 100  # [v2.8] 移除-100的保守缓冲
        if estimated_shares >= 100:  # [v2.8] 至少1手才记录（100股起步）
            strat['positions'][security] = strat['positions'].get(security, 0) + estimated_shares
            log.info('[DEBUG][%s] 虚拟持仓估算: %s +%.0f股（盘后同步修正）'
                     % (strategy_name, security, estimated_shares))

    log.info('[%s] safe_buy_value成功: %s %.2f元，策略剩余份额%.2f'
             % (strategy_name, security, value, remaining - value))
    return order_id


# ============================================================
#                    ETF策略辅助函数
# ============================================================

def get_rank_etf(etf_pool):
    """
    ETF动量因子计算

    【原理】
    - 年化收益率 × 判定系数(R²) 作为动量得分
    - 选择得分>0的前N只ETF

    【参数】
    - etf_pool: ETF代码列表

    【返回】
    - 动量得分>0的ETF列表（按得分降序，最多g.stock_num_etf只）
    """
    score_list = []

    for etf in etf_pool:
        try:
            his = get_history(g.m_days_etf, frequency='1d', field='close',
                              security_list=etf, fq='pre', include=False, is_dict=True)

            if his is None or etf not in his:
                continue

            close_array = his[etf]['close']
            if len(close_array) < g.m_days_etf:
                continue

            # 计算动量得分
            y = np.log(close_array)
            x = np.arange(len(y))
            slope, intercept = np.polyfit(x, y, 1)
            annualized_returns = math.pow(math.exp(slope), 250) - 1
            r_squared = 1 - (sum((y - (slope * x + intercept))**2) / ((len(y) - 1) * np.var(y, ddof=1)))
            score = annualized_returns * r_squared
            score_list.append({'etf': etf, 'score': score})
        except Exception as e:
            log.error('[动量] %s 计算异常: %s' % (etf, str(e)))
            continue

    if not score_list:
        return []

    df = pd.DataFrame(score_list)
    df = df.sort_values(by='score', ascending=False)

    # 筛选得分>0的
    filtered = df[df['score'] > 0]['etf'].tolist()[:g.stock_num_etf]
    return filtered


def epo_etf(x, signal, lambda_, method='anchored', w=None, anchor=None):
    """
    EPO权重优化（Enhanced Portfolio Optimization）

    【原理】
    - 收缩协方差矩阵，降低估计误差
    - 锚定等权组合，提高稳定性

    【参数】
    - x: 收益率DataFrame
    - signal: 期望收益信号
    - lambda_: 风险厌恶系数
    - method: 'simple' 或 'anchored'
    - w: 收缩权重
    - anchor: 锚定权重

    【返回】
    - 优化后的权重数组
    """
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
        if True:  # endogenous=True
            num = np.sqrt(a.T @ cov_tilde @ a)
            denom = np.sqrt(s.T @ inv_shrunk_cov @ cov_tilde @ inv_shrunk_cov @ s)
            gamma = num / denom

            term1 = (1 - w) * gamma * s
            term2 = w * I @ V @ a

            combined = term1 + term2
            epo_weights = inv_shrunk_cov @ combined

    # 归一化（负权重置0）
    epo_weights = [0 if weight < 0 else weight for weight in epo_weights]
    epo_weights = np.array(epo_weights) / np.sum(epo_weights)

    return epo_weights


def run_optimization_etf(stocks):
    """
    获取ETF价格数据并调用EPO优化

    【返回】
    - {'weights': 权重数组, 'etfs': ETF列表} 或 None
    """
    try:
        # 获取价格数据（前复权）
        his = get_history(1200, frequency='1d', field='close',
                          security_list=stocks, fq='pre', include=False, is_dict=True)

        if his is None:
            log.error('[EPO] 获取价格数据失败')
            return None

        # 构建DataFrame
        close_data = {}
        for etf in stocks:
            if etf in his:
                close_data[etf] = his[etf]['close']

        if not close_data:
            log.error('[EPO] 无有效价格数据')
            return None

        # 对齐数据长度
        min_len = min(len(arr) for arr in close_data.values())
        close_data_aligned = {etf: arr[-min_len:] for etf, arr in close_data.items()}

        close_prices = pd.DataFrame(close_data_aligned)
        close_prices = close_prices.reindex(sorted(close_prices.columns), axis=1)

        # 计算收益率
        returns = close_prices.pct_change().dropna()

        if returns.empty:
            log.error('[EPO] 收益率计算失败')
            return None

        # 计算锚定权重（等权）
        d = np.diag(returns.cov())
        if np.any(d <= 0):
            d = np.abs(d) + 0.0001  # 防止除零
        a = (1/d) / (1/d).sum()

        # 调用EPO
        weights = epo_etf(x=returns, signal=returns.mean(),
                          lambda_=g._lambda_etf, method='anchored',
                          w=g.w_etf, anchor=a)

        return {'weights': weights, 'etfs': list(close_prices.columns)}
    except Exception as e:
        log.error('[EPO] 优化失败: %s' % str(e))
        return None


# ============================================================
#                    盘前处理（融合双策略）
# ============================================================

def before_trading_start(context, data):
    """
    盘前处理 - 双策略并行

    【逻辑】
    1. 重置当日交易标志
    2. ETF策略：预计算复权因子和昨收价
    3. 小市值策略：盘前选股（如果启用）
    """
    g.current_date_etf = context.blotter.current_dt.strftime('%Y-%m-%d')

    # ==================== 重置当日标志 ====================
    # ETF策略标志
    g.trade_done_today_etf = False
    g.sell_done_etf = False
    g.buy_done_etf = False
    g.target_etfs = []
    g.target_weights = []
    g.etf_weight_map = {}

    # 小市值策略标志
    g.today_bought_stocks_small_cap = set()
    g.today_sold_stocks_small_cap = set()
    g.current_date_small_cap = context.previous_date if hasattr(context, 'previous_date') else g.current_date_etf
    g.handle_data_flag_small_cap = True
    g.buy_done_today_small_cap = False
    g.first_handle_data_done_small_cap = False

    # [v2.3新增] 全局标志位重置
    g.first_handle_data_done_global = False

    # ==================== ETF策略盘前预计算 ====================
    if g.capital_ratio_etf > 0:
        # [关键] 盘前同步ETF虚拟持仓
        _sync_virtual_positions(context, 'etf_rotation')

        # [v2.3新增] 盘前执行ETF选股（提前到盘前，用于启动对齐）
        _select_etfs_before_trading(context)

        # [调试] 记录ETF策略资金状态
        _log_strategy_capital_status(context, data, 'etf_rotation')

        # 获取复权因子和昨收价
        g.fq_factor_etf = {}
        g.yesterday_close_etf = {}

        for etf in g.etf_pool:
            try:
                # 获取除权价和前复权价
                his_raw = get_history(1, frequency='1d', field='close',
                                       security_list=etf, fq=None, include=False, is_dict=True)
                raw_price = his_raw[etf]['close'][-1] if his_raw and etf in his_raw else 0

                his_fq = get_history(1, frequency='1d', field='close',
                                      security_list=etf, fq='pre', include=False, is_dict=True)
                fq_price = his_fq[etf]['close'][-1] if his_fq and etf in his_fq else 0

                if raw_price > 0 and fq_price > 0:
                    g.fq_factor_etf[etf] = fq_price / raw_price
                    g.yesterday_close_etf[etf] = fq_price
                else:
                    g.fq_factor_etf[etf] = 1.0
                    g.yesterday_close_etf[etf] = 0
            except Exception as e:
                g.fq_factor_etf[etf] = 1.0
                g.yesterday_close_etf[etf] = 0
                log.error('[ETF盘前] %s 异常: %s' % (etf, str(e)))

    # ==================== 小市值策略盘前选股 ====================
    # 如果小市值策略启用（capital_ratio > 0），执行盘前选股
    if g.capital_ratio_small_cap > 0:
        # [关键] 盘前同步虚拟持仓（修复不一致）
        _sync_virtual_positions(context, 'small_cap')

        # [调试] 记录策略资金状态（按比例动态计算）
        _log_strategy_capital_status(context, data, 'small_cap')
        _before_trading_small_cap(context, data)

    log.info("=== 盘前处理完成 ===")


def _log_strategy_capital_status(context, data, strategy_name):
    """
    记录策略资金状态（调试日志，不影响逻辑）

    【v2.0按比例动态隔离】
    - 不需要虚拟资金池同步
    - 只记录当前状态用于调试

    【v3.1修复】排除其他策略持仓，避免资产计算混淆
    """
    capital_ratio = _get_capital_ratio(strategy_name)

    # 计算策略持仓市值
    hold_value = 0.0
    strat = g.strategies[strategy_name]

    # 排除其他策略持仓
    # 小市值策略排除货币基金和ETF池
    # ETF策略排除小市值持仓（通过虚拟持仓判断）
    money_fund = g.money_fund_small_cap if strategy_name == 'small_cap' else None
    etf_pool_set = set(g.etf_pool) if strategy_name == 'small_cap' else set()

    for code, pos in context.portfolio.positions.items():
        if pos.amount <= 0:
            continue
        if code == money_fund:
            continue
        # [v3.1新增] 排除ETF持仓（仅小市值策略）
        if code in etf_pool_set:
            continue

        try:
            price = _get_latest_price(code)
            if price and price > 0:
                hold_value += pos.amount * price
        except:
            pass

    # 计算策略可用现金
    real_cash = context.portfolio.cash
    strategy_cash = real_cash * capital_ratio

    # 策略总资产 = 持仓市值 + 可用现金
    strategy_assets = hold_value + strategy_cash

    log.info('[DEBUG][%s盘前状态] 策略总资产=%.2f (持仓=%.2f + 现金%.2f=%.0f%%)'
             % (strategy_name, strategy_assets, hold_value, strategy_cash, capital_ratio * 100))


def _sync_virtual_positions(context, strategy_name):
    """
    盘前同步虚拟持仓（v2.2关键修复）

    【问题根源】
    - 虚拟持仓可能因部分成交、订单失败等原因与真实持仓不一致
    - v2.1问题：会把所有真实持仓同步到每个策略，导致50%+50%并行时持仓混淆
    - 例如：小市值买入股票A，ETF买入股票B，盘前同步后两个策略都以为A和B是自己的持仓

    【v2.2修复方案】
    只同步本策略已有的持仓，不添加新持仓（避免混淆）：
    1. 虚拟持仓有但真实持仓不一致 → 修正虚拟持仓（以真实为准）
    2. 虚拟持仓有但真实持仓为0 → 清空虚拟持仓
    3. 真实持仓有但虚拟没有 → 不添加（保持隔离）

    【效果】
    - 小市值策略只追踪小市值买入的持仓
    - ETF策略只追踪ETF买入的持仓
    - 避免策略互相误卖对方持仓
    """
    strat = g.strategies[strategy_name]

    # [v2.1修复] 货币基金也需要被同步（不再排除）
    # 原问题：排除货币基金导致盘前同步误删虚拟持仓，冷静期退出卖出失败

    # [v2.2修复] 50%+50%并行模式下的持仓隔离
    # 只同步本策略已有的持仓，不添加新持仓（避免混淆不同策略的持仓）
    # 获取真实持仓（包含货币基金）
    real_positions = {}
    for code, pos in context.portfolio.positions.items():
        if pos.amount <= 0:
            continue
        # [v2.1] 不再排除货币基金，所有持仓都需要同步
        real_positions[code] = pos.amount

    # 对比虚拟持仓
    virtual_positions = strat['positions']

    # 检查不一致
    inconsistencies = []

    # [v2.2修复] 只检查虚拟持仓中已有的股票，不添加新股票
    for code, virtual_amt in virtual_positions.items():
        if virtual_amt <= 0:
            continue

        real_amt = real_positions.get(code, 0)

        # 真实持仓与虚拟持仓不一致
        if virtual_amt != real_amt:
            inconsistencies.append((code, virtual_amt, real_amt, 'fix'))

    # 检查虚拟持仓中有但真实持仓已清空的情况
    for code, virtual_amt in list(virtual_positions.items()):
        if virtual_amt > 0 and code not in real_positions:
            inconsistencies.append((code, virtual_amt, 0, 'delete'))

    # 修复不一致
    if inconsistencies:
        log.info('[DEBUG][%s盘前同步] 发现%d处持仓不一致:'
                 % (strategy_name, len(inconsistencies)))

        for code, v_amt, r_amt, action in inconsistencies:
            log.info('[DEBUG][%s盘前同步] %s: 虚拟=%d -> 真实=%d'
                     % (strategy_name, code, v_amt, r_amt))

            # 修复虚拟持仓（以真实持仓为准）
            if r_amt > 0:
                strat['positions'][code] = r_amt
            else:
                if code in strat['positions']:
                    del strat['positions'][code]

        log.info('[DEBUG][%s盘前同步] 已修复%d处不一致'
                 % (strategy_name, len(inconsistencies)))

    # [DEBUG] 输出同步后虚拟持仓
    synced_hold = {code: amt for code, amt in strat['positions'].items() if amt > 0}
    if synced_hold:
        log.info('[DEBUG][%s盘前同步] 虚拟持仓: %s'
                 % (strategy_name, synced_hold))

    # ==================== [v2.9新增] 盘前动态重置份额 ====================
    # 【问题根源】v2.8中，g.strategy_used只在initialize初始化为0，盘前不重置
    # 第一天买入用完份额(25000)后，第二天remaining=quota-used=25000-25000=0
    # 导致无法补买（buy_value = min(shortage, 0, cash) = 0）
    #
    # 【修复方案】盘前重置used为虚拟持仓市值：
    #   - 已用份额 = 虚拟持仓总市值（动态计算）
    #   - 可用份额 = quota - used = quota - 持仓市值 ≈ 策略可用现金
    #   - 这样第二天有份额可用于补买
    hold_value = 0
    for code, shares in strat['positions'].items():
        if shares <= 0:
            continue
        price = _get_latest_price(code)
        if price and price > 0:
            hold_value += shares * price

    # 重置已用份额为持仓市值
    old_used = g.strategy_used.get(strategy_name, 0)
    g.strategy_used[strategy_name] = hold_value

    log.info('[DEBUG][%s盘前份额重置] 持仓市值=%.2f，已用份额 %.2f -> %.2f，可用份额=%.2f'
             % (strategy_name, hold_value, old_used, hold_value,
                g.strategy_quota.get(strategy_name, 0) - hold_value))


def _select_etfs_before_trading(context):
    """
    ETF策略盘前选股（v2.3新增：提前执行，用于启动对齐）

    【目的】
    将ETF选股从月初调仓时提前到盘前，确保启动对齐时选股结果已准备好

    【调用时机】
    - 每个交易日盘前（before_trading_start中调用）
    - 只在ETF策略启用时执行（g.capital_ratio_etf > 0）

    【逻辑】
    1. 执行动量因子计算（get_rank_etf）
    2. 执行权重优化（run_optimization_etf）
    3. 存入 g.target_etfs 和 g.target_weights
    """
    if g.capital_ratio_etf <= 0:
        return

    log.info("[ETF盘前选股] 开始执行...")

    # 执行动量因子计算
    target_list = get_rank_etf(g.etf_pool)
    if not target_list:
        log.warning("[ETF盘前选股] 无符合条件的ETF")
        g.target_etfs = []
        g.target_weights = []
        g.etf_weight_map = {}
        return

    # 执行权重优化
    result = run_optimization_etf(target_list)
    if not result:
        log.warning("[ETF盘前选股] 权重优化失败，使用等权备用")
        g.target_etfs = target_list
        g.target_weights = [1.0 / len(target_list)] * len(target_list)
        g.etf_weight_map = {etf: 1.0 / len(target_list) for etf in target_list}
        return

    # 存储结果
    g.target_etfs = result['etfs']
    g.target_weights = result['weights']
    g.etf_weight_map = {etf: g.target_weights[i] for i, etf in enumerate(g.target_etfs)}

    log.info("[ETF盘前选股] 完成: 目标ETF=%s, 权重=%s"
             % (g.target_etfs, [round(w * 100, 1) for w in g.target_weights]))


def _align_startup_positions(context, data):
    """
    启动时持仓对齐（v2.3新增：检查已有持仓归属，决定卖出策略）

    【调用时机】
    - 生命周期内首次 handle_data
    - 标志位 g.first_start_done 控制只执行一次

    【核心逻辑】
    1. 获取各启用策略的买入候选
    2. 获取所有真实持仓
    3. 对每个持仓：
       - 检查是否在启用策略的买入候选中
       - 在某策略候选中 → 归属该策略，添加虚拟持仓
       - 不在任何启用策略候选中 → 卖出
    4. ETF特殊规则：持仓在ETF池但不在选股结果中 → 卖出
    5. T+1受限：记录到 g.pending_sell_stocks，第二天卖出

    【只检查启用策略】
    - 资金比例 > 0 的策略才参与归属判断
    - 例如：g.capital_ratio_etf = 0.0 时，ETF持仓检查跳过
    """
    log.info("=" * 70)
    log.info("=== [启动对齐] 开始执行持仓对齐 ===")

    # ==================== 1. 获取各启用策略的买入候选 ====================
    strategy_candidates = {}

    # 小市值候选（如果启用）
    if g.capital_ratio_small_cap > 0:
        if g.df2_small_cap is not None and not g.df2_small_cap.empty:
            df = g.df2_small_cap.copy()
            df = df.sort_values(by='float_value', ascending=True)
            candidates = df.head(g.screen_stock_count_small_cap).index.tolist()
            strategy_candidates['small_cap'] = candidates
            log.info("[启动对齐] 小市值选股结果: %s" % (candidates[:10] if len(candidates) > 10 else candidates))
        else:
            log.warning("[启动对齐] 小市值选股结果为空，无法判断持仓归属")
            strategy_candidates['small_cap'] = []

    # ETF候选（如果启用）
    if g.capital_ratio_etf > 0:
        if g.target_etfs:
            strategy_candidates['etf_rotation'] = g.target_etfs
            log.info("[启动对齐] ETF选股结果: %s" % g.target_etfs)
        else:
            log.warning("[启动对齐] ETF选股结果为空，无法判断持仓归属")
            strategy_candidates['etf_rotation'] = []

    # ==================== 2. 获取所有真实持仓 ====================
    real_positions = {}
    for code, pos in context.portfolio.positions.items():
        if pos.amount > 0:
            real_positions[code] = {
                'amount': pos.amount,
                'enable_amount': pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
            }

    if not real_positions:
        log.info("[启动对齐] 无持仓，对齐完成")
        log.info("=" * 70)
        return

    hold_codes = list(real_positions.keys())
    log.info("[启动对齐] 发现真实持仓%d只: %s" % (len(hold_codes), hold_codes))

    # ==================== 3. 归属判断与分类 ====================
    aligned_to_strategy = {}      # 归属各策略的持仓 {strategy: {code: amount}}
    to_sell_now = {}              # 立即卖出（可卖）
    to_sell_pending = {}          # 待明天卖出（T+1受限）

    for strategy_name in g.strategies.keys():
        aligned_to_strategy[strategy_name] = {}

    for code, pos_info in real_positions.items():
        amount = pos_info['amount']
        enable_amount = pos_info['enable_amount']

        # 判断归属（遍历启用策略）
        found_strategy = None
        for strategy_name, candidates in strategy_candidates.items():
            if code in candidates:
                found_strategy = strategy_name
                break

        # ETF池特殊处理：如果ETF策略启用，持仓在ETF池但不在选股结果中 → 卖出
        if g.capital_ratio_etf > 0 and code in g.etf_pool and found_strategy != 'etf_rotation':
            found_strategy = None  # 强制设置为不属于任何策略

        # 分类处理
        if found_strategy:
            # 归属某策略 → 保留
            aligned_to_strategy[found_strategy][code] = amount
            log.info("[启动对齐] %s → 归属%s策略，保留%d股" % (code, found_strategy, amount))
        else:
            # 不属于任何启用策略 → 卖出
            if enable_amount > 0:
                to_sell_now[code] = enable_amount
                log.info("[启动对齐] %s → 不属于任何启用策略，卖出%d股" % (code, enable_amount))
            else:
                to_sell_pending[code] = amount
                log.info("[启动对齐] %s → 不属于任何启用策略，T+1受限，待明天卖出%d股" % (code, amount))

    # ==================== 4. 更新虚拟持仓 ====================
    for strategy_name, positions in aligned_to_strategy.items():
        for code, amount in positions.items():
            g.strategies[strategy_name]['positions'][code] = amount

    # ==================== 5. 执行立即卖出 ====================
    sold_count = 0
    for code, amount in to_sell_now.items():
        try:
            # 使用普通order函数卖出（不属于任何策略，不需要safe_sell）
            order_id = order(code, -amount)
            if order_id:
                sold_count += 1
                log.info("[启动对齐] 卖出成功: %s x %d股" % (code, amount))
            else:
                log.error("[启动对齐] 卖出失败: %s" % code)
                # 卖出失败也加入待卖出列表
                to_sell_pending[code] = amount
        except Exception as e:
            log.error("[启动对齐] 卖出异常: %s, %s" % (code, str(e)))
            to_sell_pending[code] = amount

    # ==================== 6. 记录待卖出（T+1受限）====================
    for code, amount in to_sell_pending.items():
        g.pending_sell_stocks[code] = {'amount': amount}
        log.info("[启动对齐] 记录待卖出: %s = %d股（T+1受限或卖出失败）" % (code, amount))

    # ==================== 7. 输出对齐结果 ====================
    log.info("--- [启动对齐] 结果汇总 ---")
    for strategy_name, positions in aligned_to_strategy.items():
        if positions:
            log.info("  %s保留: %d只 - %s" % (strategy_name, len(positions), list(positions.keys())))
        else:
            log.info("  %s保留: 0只" % strategy_name)

    log.info("  立即卖出: %d只" % sold_count)
    log.info("  待卖出(T+1): %d只" % len(to_sell_pending))

    log.info("=== [启动对齐] 完成 ===")
    log.info("=" * 70)


def _process_pending_sell_stocks(context, data):
    """
    处理待卖出股票（v2.3新增：处理前一天T+1受限的）

    【调用时机】
    - 每天首次 handle_data（在启动对齐之后）
    - 标志位 g.first_handle_data_done_global 控制每天只执行一次

    【逻辑】
    1. 检查 g.pending_sell_stocks
    2. 对每个待卖出股票，检查是否可卖（enable_amount > 0）
    3. 可卖 → 执行卖出，从待卖出列表删除
    4. 不可卖 → 继续等待（保持待卖出状态）
    """
    if not g.pending_sell_stocks:
        return

    log.info("[待卖出处理] 开始处理前一天T+1受限股票...")

    pending_codes = list(g.pending_sell_stocks.keys())
    log.info("[待卖出处理] 待卖出列表: %s" % pending_codes)

    sold_count = 0
    remain_count = 0

    for code in pending_codes:
        info = g.pending_sell_stocks[code]
        amount = info['amount']

        try:
            pos = get_position(code)
            if not pos or pos.amount <= 0:
                # 持仓已不存在（可能已卖出或其他原因）
                del g.pending_sell_stocks[code]
                log.info("[待卖出处理] %s: 持仓已不存在，清理" % code)
                continue

            enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount

            if enable_amount > 0:
                # 可卖 → 执行卖出
                sell_amount = min(amount, enable_amount)
                order_id = order(code, -sell_amount)
                if order_id:
                    del g.pending_sell_stocks[code]
                    sold_count += 1
                    log.info("[待卖出处理] %s: 卖出%d股，成功" % (code, sell_amount))
                else:
                    log.error("[待卖出处理] %s: 卖出失败" % code)
                    remain_count += 1
            else:
                # 仍不可卖 → 继续等待
                remain_count += 1
                log.warning("[待卖出处理] %s: T+1仍受限，继续等待" % code)
        except Exception as e:
            log.error("[待卖出处理] %s: 异常 %s" % (code, str(e)))
            remain_count += 1

    log.info("[待卖出处理] 完成: 卖出%d只, 待卖出%d只" % (sold_count, remain_count))


def _before_trading_small_cap(context, data):
    """
    小市值策略盘前选股逻辑（内部函数）

    【逻辑】
    1. 冷静期/空仓月检查
    2. 组合跌幅检查
    3. ROE筛选
    4. 市值筛选
    """
    # 冷静期处理
    if g.in_cooldown_small_cap:
        g.days_since_sell_small_cap = _trading_days_since_last_sell_small_cap(context)
        log.info("[小市值盘前] 冷静期 %d/%d" % (g.days_since_sell_small_cap, g.cooldown_days_small_cap))
        g.df2_small_cap = None
        return

    # 空仓月处理
    if _is_empty_month_small_cap(context):
        # [v2.1修复] 只有在空仓月清仓未执行时才触发
        if not g.empty_month_clear_done:
            g.trigger_empty_month_small_cap = True
            log.info("[小市值盘前] 空仓月开始")
        g.df2_small_cap = None
        return
    else:
        # [v2.1修复] 非空仓月时重置标志位
        g.empty_month_clear_done = False

    # 盘前预存昨除权价
    g.yesterday_close_small_cap = {}
    hold_codes = [s for s, p in context.portfolio.positions.items() if p.amount > 0
                  and s != g.money_fund_small_cap]

    for code in hold_codes:
        try:
            his = get_history(1, frequency='1d', field='close',
                              security_list=code, fq=None, include=False, is_dict=True)
            if his and code in his:
                yclose = float(his[code]['close'][-1])
                if yclose > 0:
                    g.yesterday_close_small_cap[code] = yclose
        except:
            pass

    # 组合跌幅检查
    if g.in_cooldown_small_cap or _is_empty_month_small_cap(context):
        g.portfolio_values_small_cap = []
    else:
        strategy_assets = _get_strategy_assets_small_cap(context, data)
        g.portfolio_values_small_cap.append(strategy_assets)
        if len(g.portfolio_values_small_cap) > 4:
            g.portfolio_values_small_cap.pop(0)

        if check_portfolio_decline_small_cap(context):
            g.df2_small_cap = None
            return

    # 选股流程
    stock_pool = _get_universe_small_cap(context)
    if not stock_pool:
        log.warning("[小市值选股] 股票池为空")
        g.df2_small_cap = None
        return

    # ROE筛选
    if g.roe_filter_small_cap:
        stock_pool = _filter_by_roe_small_cap(context, stock_pool)
        if not stock_pool:
            g.df2_small_cap = None
            return

    # ROE改善筛选
    if g.roe_improve_filter_small_cap:
        stock_pool = _filter_by_roe_improve_small_cap(context, stock_pool)
        if not stock_pool:
            g.df2_small_cap = None
            return

    # 获取市值数据
    try:
        df = get_fundamentals(stock_pool, "valuation",
                              fields=["float_value", "a_floats"],
                              date=g.current_date_small_cap)
        if df is None or df.empty:
            g.df2_small_cap = None
            return

        if isinstance(df.index, pd.MultiIndex):
            df_reset = df.reset_index()
            df_reset = df_reset.sort_values(by='end_date', ascending=False)
            df = df_reset.drop_duplicates(subset='secu_code', keep='first')
            df = df.set_index('secu_code')

        # 转换成亿元
        df['float_value'] = df['float_value'] / 100000000.0

        g.df2_small_cap = df

        # 更新股票池订阅
        stock_codes = list(g.df2_small_cap.index)
        set_universe(stock_codes + g.etf_pool)

        log.info("[小市值选股] 最终数量: %d" % len(g.df2_small_cap))
    except Exception as e:
        log.error("[小市值选股] 市值数据失败: %s" % str(e))
        g.df2_small_cap = None


# ============================================================
#                    小市值辅助函数（部分）
# ============================================================

def _trading_days_since_last_sell_small_cap(context):
    """计算距离上次卖出的交易日数"""
    if not g.last_sell_date_small_cap:
        return 0
    try:
        last = datetime.strptime(g.last_sell_date_small_cap, '%Y-%m-%d').date()
        current = context.blotter.current_dt.date()
        return (current - last).days
    except:
        return 0


def _is_empty_month_small_cap(context):
    """检查是否是空仓月"""
    try:
        return context.blotter.current_dt.month in g.empty_months_small_cap
    except:
        return False


def _is_first_trading_day_in_month_small_cap(context):
    """检查是否是月初第一个交易日"""
    try:
        return context.blotter.current_dt.date().day <= 3
    except:
        return False


def _is_last_trading_day_in_month_small_cap(context):
    """检查是否是月末最后一个交易日"""
    try:
        return context.blotter.current_dt.date().day >= 28
    except:
        return False


def _get_strategy_assets_small_cap(context, data):
    """计算小市值策略资产（股票持仓市值，排除货币基金和ETF持仓）

    【v3.1修复】当ETF策略并行运行时，需要排除ETF持仓，避免资产计算混淆
    """
    total = 0.0
    etf_pool_set = set(g.etf_pool)  # ETF池

    for code, pos in context.portfolio.positions.items():
        if pos.amount <= 0:
            continue
        if code == g.money_fund_small_cap:
            continue
        # [v3.1新增] 排除ETF持仓
        if code in etf_pool_set:
            continue
        try:
            if code in data:
                price = data[code].price
            else:
                his = get_history(1, frequency='1d', field='close',
                                   security_list=code, fq=None, include=False, is_dict=True)
                if his and code in his:
                    price = float(his[code]['close'][-1])
                else:
                    price = 0
            if price > 0:
                total += pos.amount * price
        except:
            pass
    return total


def _get_universe_small_cap(context):
    """获取小市值股票池"""
    try:
        pool = get_index_stocks(g.index_small_cap)
        return _filter_st_pause_delist(pool)
    except Exception as e:
        log.error("[小市值股票池] 失败: %s" % str(e))
        return []


def _filter_st_pause_delist(codes):
    """过滤ST/停牌/退市股票"""
    if not codes:
        return []
    try:
        return filter_stock_by_status(codes, filter_type=["ST", "HALT", "DELISTING"])
    except Exception as e:
        log.error("[过滤] 失败: %s" % str(e))
        return codes


def check_portfolio_decline_small_cap(context):
    """检查策略资产连续下跌"""
    need_num = g.decline_days_small_cap

    if len(g.portfolio_values_small_cap) < need_num + 1:
        return False

    if g.portfolio_values_small_cap[-1] <= 0:
        return False

    decline_days = 0
    decline_details = []

    for i in range(need_num):
        newer = g.portfolio_values_small_cap[-(i+1)]
        older = g.portfolio_values_small_cap[-(i+2)]
        if older > 0:
            daily_ret = (newer - older) / older
            is_decline = daily_ret <= g.decline_threshold_small_cap
            decline_details.append({
                'day': i+1, 'new': newer, 'old': older,
                'ret': daily_ret, 'trigger': is_decline
            })
            if is_decline:
                decline_days += 1

    if decline_days >= need_num:
        log.info('[冷静期触发] 策略资产连续%d天跌幅超阈值%.2f%%'
                 % (need_num, g.decline_threshold_small_cap * 100))
        for detail in decline_details:
            log.info("  第%d天: %.2f -> %.2f, 跌幅=%.2f%%"
                     % (detail['day'], detail['old'], detail['new'], detail['ret'] * 100))

        g.trigger_cooldown_small_cap = True
        g.in_cooldown_small_cap = True
        g.cooldown_count_small_cap += 1
        d = context.blotter.current_dt.strftime('%Y-%m-%d')
        g.cooldown_dates_small_cap.append(d)
        g.last_sell_date_small_cap = d
        g.days_since_sell_small_cap = 0
        g.portfolio_values_small_cap = []

        log.info('[冷静期] 日期: %s, 累计次数: %d' % (d, g.cooldown_count_small_cap))
        return True

    return False


# ============================================================
#                    ROE筛选函数（小市值）
# ============================================================

def _get_financial_data_small_cap(stock_list, start_year, end_year):
    """获取财报数据"""
    try:
        np_df = get_fundamentals(stock_list, "income_statement",
                                  fields=["np_parent_company_owners"],
                                  start_year=start_year, end_year=end_year)
        eq_df = get_fundamentals(stock_list, "balance_statement",
                                  fields=["total_shareholder_equity"],
                                  start_year=start_year, end_year=end_year)

        if np_df is None or np_df.empty or eq_df is None or eq_df.empty:
            return None

        if isinstance(np_df.index, pd.MultiIndex):
            np_reset = np_df.reset_index()
            eq_reset = eq_df.reset_index()
        else:
            return None

        np_reset = np_reset.rename(columns={'np_parent_company_owners': 'np'})
        eq_reset = eq_reset.rename(columns={'total_shareholder_equity': 'equity'})

        merged = pd.merge(
            np_reset[['secu_code', 'end_date', 'np']],
            eq_reset[['secu_code', 'end_date', 'equity']],
            on=['secu_code', 'end_date'], how='inner'
        )
        return merged
    except Exception as e:
        log.error("[财报] 获取失败: %s" % str(e))
        return None


def _calc_single_quarter_roe_small_cap(financial_df):
    """计算单季度ROE"""
    if financial_df is None or financial_df.empty:
        return None

    results = []
    grouped = financial_df.groupby('secu_code')

    for stock, group in grouped:
        date_data = {}
        for _, row in group.iterrows():
            parts = row['end_date'].split('-')
            year, month = int(parts[0]), int(parts[1])
            date_data[(year, month)] = {
                'np': row['np'], 'equity': row['equity'], 'end_date': row['end_date']
            }

        for (year, month), d in date_data.items():
            curr_np, curr_equity, end_date = d['np'], d['equity'], d['end_date']

            if month == 3:
                single_np = curr_np
            elif month == 6:
                if (year, 3) in date_data:
                    single_np = curr_np - date_data[(year, 3)]['np']
                else:
                    continue
            elif month == 9:
                if (year, 6) in date_data:
                    single_np = curr_np - date_data[(year, 6)]['np']
                else:
                    continue
            elif month == 12:
                if (year, 9) in date_data:
                    single_np = curr_np - date_data[(year, 9)]['np']
                else:
                    continue
            else:
                continue

            roe = (single_np / curr_equity) * 100 if curr_equity > 0 else 0
            results.append({'secu_code': stock, 'end_date': end_date, 'roe': roe})

    return pd.DataFrame(results) if results else None


def _get_latest_quarter_date_small_cap(current_date):
    """获取最近的财报季度"""
    year = int(str(current_date)[:4])
    month = int(str(current_date)[5:7])

    if month <= 3:
        return "%d-09-30" % (year - 1)
    elif month <= 6:
        return "%d-12-31" % (year - 1)
    elif month <= 9:
        return "%d-06-30" % year
    else:
        return "%d-09-30" % year


def _filter_by_roe_small_cap(context, stock_list):
    """ROE筛选"""
    if not stock_list:
        return []

    try:
        current_year = int(str(g.current_date_small_cap)[:4])
        financial_df = _get_financial_data_small_cap(stock_list, str(current_year - 1), str(current_year))

        if financial_df is None or financial_df.empty:
            return stock_list

        roe_df = _calc_single_quarter_roe_small_cap(financial_df)
        if roe_df is None or roe_df.empty:
            return stock_list

        latest_quarter = _get_latest_quarter_date_small_cap(g.current_date_small_cap)
        roe_quarter = roe_df[roe_df['end_date'] == latest_quarter].copy()

        if roe_quarter.empty:
            roe_df = roe_df.sort_values('end_date', ascending=False)
            roe_quarter = roe_df.drop_duplicates(subset='secu_code', keep='first')

        roe_quarter = roe_quarter.set_index('secu_code')
        roe_quarter = roe_quarter[roe_quarter['roe'] > g.roe_threshold_small_cap]

        return roe_quarter.index.tolist()
    except Exception as e:
        log.error("[ROE筛选] 失败: %s" % str(e))
        return stock_list


def _filter_by_roe_improve_small_cap(context, stock_list):
    """ROE改善筛选"""
    if not stock_list:
        return []

    try:
        current_year = int(str(g.current_date_small_cap)[:4])
        financial_df = _get_financial_data_small_cap(stock_list, str(current_year - 3), str(current_year))

        if financial_df is None or financial_df.empty:
            return stock_list

        roe_df = _calc_single_quarter_roe_small_cap(financial_df)
        if roe_df is None or roe_df.empty:
            return stock_list

        latest_quarter = _get_latest_quarter_date_small_cap(g.current_date_small_cap)
        all_dates = sorted(roe_df['end_date'].unique())

        if latest_quarter in all_dates:
            latest_idx = all_dates.index(latest_quarter)
            latest_5 = all_dates[max(0, latest_idx-4):latest_idx+1] if latest_idx >= 4 else all_dates[-5:]
        else:
            latest_5 = all_dates[-5:]

        if len(latest_5) < 5:
            return stock_list

        roe_pivot = roe_df.pivot_table(index='secu_code', columns='end_date', values='roe')

        # 过滤ROE异常
        for d in latest_5:
            if d in roe_pivot.columns:
                roe_pivot = roe_pivot[(roe_pivot[d].abs() <= 100) | (roe_pivot[d].isna())]

        # 计算改善值
        roe_pivot['increase'] = 4 * roe_pivot[latest_5[4]] - roe_pivot[latest_5[0]] - \
                                roe_pivot[latest_5[1]] - roe_pivot[latest_5[2]] - roe_pivot[latest_5[3]]

        roe_pivot = roe_pivot.dropna(subset=['increase'])
        roe_pivot = roe_pivot.sort_values(by='increase', ascending=False)

        top_count = max(1, int(len(roe_pivot) * g.roe_improve_top_small_cap))
        return roe_pivot.head(top_count).index.tolist()
    except Exception as e:
        log.error("[ROE改善] 失败: %s" % str(e))
        return stock_list


# ============================================================
#                    handle_data（时间调度核心）
# ============================================================

def handle_data(context, data):
    """
    分钟回调 - 时间调度核心

    【v2.3时间分发规则】
    优先级从高到低：
    1. 启动时持仓对齐（生命周期内首次handle_data）
    2. 处理待卖出股票（每天首次handle_data）
    3. 14:49 → 小市值卖出（如果启用）
    4. 10:30/13:30/14:30 → 小市值冷静期检查（如果启用）
    5. 首次handle_data → 执行冷静期/空仓月清仓（如果触发）
    6. 月初调仓日（<14:40）→ ETF轮动（先卖后买，分两分钟）
    7. 其他时间 → 小市值分钟止盈 + 买入检查
    """
    hour = context.blotter.current_dt.hour
    minute = context.blotter.current_dt.minute
    time_str = "%02d:%02d" % (hour, minute)
    current_month = context.blotter.current_dt.month

    # ==================== [v2.3新增] 启动时持仓对齐（最高优先级）====================
    # 生命周期内只执行一次，在所有其他逻辑之前
    if not g.first_start_done:
        g.first_start_done = True
        _align_startup_positions(context, data)
        # [v2.3修改] 对齐后继续执行买入检查（不return），确保持仓金额分配到位
        # 原问题：持仓数量达标但金额不足，现金闲置

    # ==================== [v2.3新增] 处理待卖出股票（每天首次）====================
    # 处理前一天T+1受限的股票
    if g.pending_sell_stocks and not g.first_handle_data_done_global:
        g.first_handle_data_done_global = True
        _process_pending_sell_stocks(context, data)
        return  # 处理完成后等待下一分钟

    # ==================== 14:49 固定卖出（小市值）====================
    if time_str == '14:49' and g.capital_ratio_small_cap > 0:
        sell_stocks_small_cap(context, data)
        return

    # ==================== 冷静期检查（小市值）====================
    if time_str in ['10:30', '13:30', '14:30'] and g.capital_ratio_small_cap > 0:
        check_cooldown_small_cap(context, data)
        return

    # ==================== 首次handle_data：冷静期/空仓月清仓 ====================
    if not g.first_handle_data_done_small_cap and g.capital_ratio_small_cap > 0:
        g.first_handle_data_done_small_cap = True

        if g.trigger_cooldown_small_cap:
            _execute_cooldown_clear_small_cap(context, data)
            g.trigger_cooldown_small_cap = False
            return

        if g.trigger_empty_month_small_cap:
            _execute_empty_month_clear_small_cap(context, data)
            g.trigger_empty_month_small_cap = False
            g.empty_month_clear_done = True  # [v2.1修复] 标记空仓月清仓已执行
            return

    # ==================== [v2.8调整] 小市值买入（优先于ETF）===================
    # 用户需求：小市值股票波动大，开盘尽早买入；ETF波动小，晚一两分钟也行
    if g.capital_ratio_small_cap > 0:
        if '09:30' <= time_str <= '14:40' and not g.buy_done_today_small_cap and g.handle_data_flag_small_cap:
            buy_stocks_small_cap(context, data)
            return

        # 其他时间：分钟止盈
        interval_sell_buy_small_cap(context, data)

    # ==================== ETF月初调仓（分两分钟执行）===================
    # [v2.8调整] 移到小市值买入之后，确保小市值先买
    if g.capital_ratio_etf > 0:
        if current_month != g.last_trade_month_etf and time_str < '14:40' and not g.trade_done_today_etf:
            # 第一分钟：卖出
            if not g.sell_done_etf:
                sell_etfs(context, data)
                g.sell_done_etf = True
                return

            # 第二分钟：买入
            if g.sell_done_etf and not g.buy_done_etf:
                buy_etfs(context, data)
                g.buy_done_etf = True
                g.trade_done_today_etf = True
                g.last_trade_month_etf = current_month
                return

# ============================================================
#                    ETF策略买卖函数
# ============================================================

def sell_etfs(context, data):
    """
    ETF策略卖出逻辑（月初调仓第一阶段）

    【v2.3修复】
    - 只检查ETF池中的持仓，避免误卖小市值策略持仓
    """
    log.info("=" * 50)
    log.info("=== ETF月初调仓 - 卖出阶段 ===")

    # [v2.3修复] 使用盘前选股结果（已在before_trading_start中计算）
    if not g.target_etfs:
        # 如果盘前选股失败，重新执行选股
        target_list = get_rank_etf(g.etf_pool)
        if not target_list:
            log.warning("[ETF] 无法获取目标ETF，跳过调仓")
            g.last_trade_month_etf = context.blotter.current_dt.month
            g.trade_done_today_etf = True
            return

        result = run_optimization_etf(target_list)
        if not result:
            log.warning("[ETF] 无法计算权重，跳过调仓")
            g.last_trade_month_etf = context.blotter.current_dt.month
            g.trade_done_today_etf = True
            return

        g.target_etfs = target_list
        g.target_weights = result['weights']
        g.etf_weight_map = {etf: g.target_weights[i] for i, etf in enumerate(g.target_etfs)}
    else:
        log.info("[ETF卖出] 使用盘前选股结果: %s" % g.target_etfs)

    total_value = context.portfolio.total_value
    strategy_capital = total_value * g.capital_ratio_etf

    log.info("[ETF资金] 总资产: %.2f, 策略资金: %.2f (%.0f%%)"
             % (total_value, strategy_capital, g.capital_ratio_etf * 100))
    log.info("--- 目标ETF及权重 ---")
    for i, etf in enumerate(g.target_etfs):
        w = g.target_weights[i]
        target_amt = strategy_capital * w
        log.info("  %s: 权重=%.2f%%, 目标金额=%.2f" % (etf, w * 100, target_amt))

    # [v2.3修复] 只检查ETF池中的持仓，避免误卖小市值策略持仓
    etf_pool_set = set(g.etf_pool)

    # 执行卖出（只遍历ETF池中的持仓）
    for etf in etf_pool_set:
        try:
            pos = get_position(etf)
            if not pos or pos.amount <= 0:
                continue

            weight = g.etf_weight_map.get(etf, 0)

            # 获取实时价格（前复权）
            raw_price = data[etf].price if etf in data and hasattr(data[etf], 'price') else 0
            fq_factor = g.fq_factor_etf.get(etf, 1.0)
            price = raw_price * fq_factor

            if price <= 0:
                log.error("[ETF卖出] %s 无法获取价格，跳过" % etf)
                continue

            # 计算目标股数
            if weight <= 0 or etf not in g.target_etfs:
                # 清仓
                sell_shares = pos.amount
                log.info("[ETF卖出] %s: 清仓 %d股（不在目标池）" % (etf, sell_shares))
            else:
                # 减仓
                target_shares = int(strategy_capital * weight / price / 100) * 100
                if pos.amount > target_shares:
                    sell_shares = pos.amount - target_shares
                    log.info("[ETF卖出] %s: 减仓 %d股 (当前=%d, 目标=%d)"
                             % (etf, sell_shares, pos.amount, target_shares))
                else:
                    sell_shares = 0

            # 拆单卖出
            if sell_shares > 0:
                safe_sell(context, 'etf_rotation', etf, sell_shares, limit_price=raw_price)
        except Exception as e:
            log.error("[ETF卖出] %s 异常: %s" % (etf, str(e)))


def buy_etfs(context, data):
    """
    ETF策略买入逻辑（月初调仓第二阶段）

    【v2.6修改】
    - 使用固定份额池（quota - used）限制买入金额
    - 目标金额基于固定份额quota，而不是动态资产
    - 解决并行模式份额分配问题

    【逻辑】
    1. 按权重计算每个ETF的目标金额（基于固定份额）
    2. 涨停过滤
    3. 用剩余份额限制买入金额
    4. 拆单买入
    """
    log.info("=== ETF月初调仓 - 买入阶段 ===")

    cash = context.portfolio.cash

    # [v2.6] 使用固定份额池，而不是动态资产
    quota = g.strategy_quota.get('etf_rotation', 0)
    used = g.strategy_used.get('etf_rotation', 0)
    remaining_quota = quota - used
    strategy_capital = quota  # 固定份额作为策略资金

    log.info("[ETF买入] 当前现金: %.2f, ETF剩余份额: %.2f (总额%.2f - 已用%.2f)"
             % (cash, remaining_quota, quota, used))

    for i, etf in enumerate(g.target_etfs):
        w = g.target_weights[i]
        if w <= 0:
            continue

        # 目标金额
        target_value = strategy_capital * w

        # 获取当前持仓市值
        try:
            pos = get_position(etf)
            current_value = pos.market_value if pos and hasattr(pos, 'market_value') else 0
        except:
            current_value = 0

        # 获取实时价格
        raw_price = data[etf].price if etf in data and hasattr(data[etf], 'price') else 0
        fq_factor = g.fq_factor_etf.get(etf, 1.0)
        price = raw_price * fq_factor
        yesterday_close = g.yesterday_close_etf.get(etf, 0)

        if price <= 0:
            log.error("[ETF买入] %s 无法获取价格，跳过" % etf)
            continue

        # 涨停判断
        try:
            code = etf.split('.')[0]
            limit_rate = 0.20 if code.startswith('688') or code.startswith('300') else 0.10
            up_limit = yesterday_close * (1 + limit_rate)

            if price >= up_limit * 0.995:
                log.warning("[ETF买入] %s 涨停中，跳过" % etf)
                continue
        except:
            pass

        # 需买入金额
        need_buy_value = target_value - current_value
        if need_buy_value <= 100:
            log.info("[ETF买入] %s: 无需买入（差额=%.2f）" % (etf, need_buy_value))
            continue

        # [v2.6] 实际买入金额（不超过剩余份额和真实现金）
        # 刷新剩余份额（因为safe_buy_value会更新used）
        used_now = g.strategy_used.get('etf_rotation', 0)
        remaining_quota_now = quota - used_now
        actual_buy_value = min(need_buy_value, remaining_quota_now, cash)
        if actual_buy_value < 100:
            log.warning("[ETF买入] %s: 份额/资金不足，跳过 (需=%.2f, 剩余份额=%.2f, 现金=%.2f)"
                        % (etf, need_buy_value, remaining_quota_now, cash))
            continue

        log.info("[ETF买入] %s: 目标=%.2f, 当前=%.2f, 买入=%.2f (剩余份额=%.2f)"
                 % (etf, target_value, current_value, actual_buy_value, remaining_quota_now))

        # 拆单买入
        max_value_per_order = 900000 * price * 0.95 if price > 0 else 500000
        remaining_value = actual_buy_value

        while remaining_value > 0:
            batch_value = min(remaining_value, max_value_per_order)
            if batch_value > 0:
                safe_buy_value(context, 'etf_rotation', etf, batch_value, limit_price=raw_price)
                remaining_value -= batch_value
            else:
                break

        cash -= actual_buy_value

    log.info("=== ETF调仓完成 ===")


# ============================================================
#                    小市值策略买卖函数
# ============================================================

def buy_stocks_small_cap(context, data):
    """
    小市值买入逻辑（交易时间内任意时间点执行一次）

    【v2.7修改】
    - 使用固定份额池计算策略资金（quota - used）
    - 解决并行模式份额分配问题

    【v2.3修改】
    - 不只看持仓数量，还要检查金额分配
    - 如果持仓金额不足（低于目标的80%），补买该持仓
    - 确保资金充分利用
    """
    if g.buy_done_today_small_cap:
        return

    if not g.handle_data_flag_small_cap:
        return

    # 冷静期/空仓月不买入
    if g.in_cooldown_small_cap or _is_empty_month_small_cap(context):
        return

    # 获取目标股票
    targets = _get_trade_stocks_small_cap(context, data, mode='buy')
    if not targets:
        g.buy_done_today_small_cap = True
        return

    # ==================== [v2.7] 资金计算（使用固定份额）====================
    quota = g.strategy_quota.get('small_cap', 0)
    used = g.strategy_used.get('small_cap', 0)
    remaining_quota = quota - used
    strategy_capital = quota  # 固定份额作为策略资金
    per_value = strategy_capital / float(g.buy_stock_count_small_cap) if g.buy_stock_count_small_cap > 0 else 0

    # ==================== [v3.0移除] 不再检查持仓金额分配 ====================
    # 原v2.3补买逻辑已移除，补买导致超跌和更大亏损
    # 只买入新股票，不再补买现有持仓

    # [v2.3修复] 只计算小市值策略的虚拟持仓，排除ETF持仓
    etf_pool_set = set(g.etf_pool)
    held = [s for s, p in context.portfolio.positions.items() if p.amount > 0 and s not in etf_pool_set]
    need_num = g.buy_stock_count_small_cap - len(held)

    # ==================== 买入逻辑 ====================
    current_time = context.blotter.current_dt.strftime('%H:%M')

    if need_num > 0:
        log.info("[小市值买入] %s, 策略资金%.2f, 每只%.2f, 需买入%d只 (剩余份额%.2f)"
                 % (current_time, strategy_capital, per_value, need_num, remaining_quota))
    else:
        # 持仓数量达标，跳过买入
        log.info("[小市值买入] %s, 持仓数量达标（%d只），跳过" % (current_time, len(held)))
        g.buy_done_today_small_cap = True
        return

    bought_count = 0

    # ==================== [v3.0简化] 只买入新股票，不再补买 ====================
    for code in targets:
        if code in held:
            continue
        if per_value <= 0:
            break
        if need_num <= 0:
            break

        try:
            price = data[code].price if code in data else 0
            if price <= 0:
                continue

            # 涨停过滤
            yclose = g.yesterday_close_small_cap.get(code, 0)
            if yclose > 0 and price >= yclose * 1.095:
                log.warning("[买入] %s 涨停中，跳过" % code)
                continue

            # 拆单买入
            max_value_per_order = 900000 * price * 0.95
            remaining_value = per_value
            cash = context.portfolio.cash

            while remaining_value > 0 and cash > 0:
                batch_value = min(remaining_value, max_value_per_order, cash * g.capital_ratio_small_cap)
                if batch_value > 0:
                    order_id = safe_buy_value(context, 'small_cap', code, batch_value)
                    if order_id:
                        remaining_value -= batch_value
                        cash -= batch_value
                    else:
                        break
                else:
                    break

            g.today_bought_stocks_small_cap.add(code)
            held.append(code)
            need_num -= 1
            bought_count += 1

            # 存储昨收价
            if code not in g.yesterday_close_small_cap:
                try:
                    his = get_history(1, frequency='1d', field='close',
                                       security_list=code, fq=None, include=False, is_dict=True)
                    if his and code in his:
                        yclose = float(his[code]['close'][-1])
                        if yclose > 0:
                            g.yesterday_close_small_cap[code] = yclose
                except:
                    pass

            if need_num <= 0:
                break
        except Exception as e:
            log.error("[小市值买入] %s 失败: %s" % (code, str(e)))

    if bought_count > 0:
        log.info("[小市值买入] 完成: 买入%d只" % bought_count)

    g.buy_done_today_small_cap = True


def sell_stocks_small_cap(context, data):
    """
    小市值卖出逻辑（14:49）

    【v2.3修复】
    - 跳过ETF池中的持仓（避免误卖ETF策略持仓）
    - 只有safe_sell成功才计数
    """
    if not g.handle_data_flag_small_cap:
        return

    targets = _get_trade_stocks_small_cap(context, data, mode='sell')
    target_set = set(targets)

    # [v2.3修复] ETF池集合，用于过滤ETF持仓
    etf_pool_set = set(g.etf_pool)

    sold_count = 0
    for code, pos in list(context.portfolio.positions.items()):
        try:
            if pos.amount <= 0:
                continue

            # [v2.3修复] 跳过ETF池中的持仓（ETF策略持仓）
            if code in etf_pool_set:
                continue

            enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount

            # 货币基金处理
            if code == g.money_fund_small_cap:
                if g.in_cooldown_small_cap:
                    continue
                if _is_empty_month_small_cap(context) and _is_last_trading_day_in_month_small_cap(context):
                    if enable_amount > 0:
                        order_id = safe_sell(context, 'small_cap', code, enable_amount)
                        if order_id:
                            log.info('[小市值14:49] 空仓月月末，卖出货基')
                continue

            # 不在目标列表则卖出
            if code not in target_set:
                if enable_amount > 0:
                    order_id = safe_sell(context, 'small_cap', code, enable_amount)
                    # [v2.3修复] 只有safe_sell成功才计数和记录
                    if order_id:
                        g.today_sold_stocks_small_cap.add(code)
                        g.last_sell_date_small_cap = context.blotter.current_dt.strftime('%Y-%m-%d')
                        sold_count += 1
        except Exception as e:
            log.error('[小市值卖出] %s 异常: %s' % (code, str(e)))

    if sold_count > 0:
        log.info("[小市值14:49] 完成: 卖出%d只" % sold_count)


def interval_sell_buy_small_cap(context, data):
    """
    小市值分钟级风控（止盈）

    【v2.3修复】
    - 跳过ETF池中的持仓（避免误检查ETF策略持仓）
    """
    if _is_empty_month_small_cap(context) or g.in_cooldown_small_cap:
        return

    today_str = str(context.blotter.current_dt.date())

    # [v2.3修复] ETF池集合，用于过滤ETF持仓
    etf_pool_set = set(g.etf_pool)

    for code, pos in list(context.portfolio.positions.items()):
        try:
            if pos.amount <= 0:
                continue

            # [v2.3修复] 跳过ETF池中的持仓
            if code in etf_pool_set:
                continue

            if code == g.money_fund_small_cap:
                continue

            # T+1检查
            enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
            if enable_amount <= 0:
                continue

            # 涨幅计算
            yclose = g.yesterday_close_small_cap.get(code, 0)
            if yclose <= 0:
                continue

            if code not in data:
                continue

            current_price = data[code].price
            pct = (current_price / yclose - 1.0) * 100.0

            # 止盈
            if pct >= g.uprate_small_cap and code not in g.today_sold_stocks_small_cap:
                log.info('[小市值止盈] %s: 涨幅=%.2f%%, 可卖=%d股' % (code, pct, enable_amount))
                safe_sell(context, 'small_cap', code, enable_amount)
                g.today_sold_stocks_small_cap.add(code)
                g.sold_stocks_dates_small_cap[code] = today_str
                g.last_sell_date_small_cap = today_str
        except Exception as e:
            log.error('[小市值止盈] %s 失败: %s' % (code, str(e)))


def check_cooldown_small_cap(context, data):
    """
    小市值冷静期管理
    """
    if not g.in_cooldown_small_cap:
        return

    g.days_since_sell_small_cap = _trading_days_since_last_sell_small_cap(context)

    # 到期退出
    if g.days_since_sell_small_cap >= g.cooldown_days_small_cap:
        log.info("[小市值冷静期] 到期退出 (%d天)" % g.cooldown_days_small_cap)

        # 卖出货币基金
        try:
            if g.money_fund_small_cap in context.portfolio.positions:
                pos = context.portfolio.positions[g.money_fund_small_cap]
                enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
                if enable_amount >= 100:
                    safe_sell(context, 'small_cap', g.money_fund_small_cap, enable_amount)
        except Exception as e:
            log.error('[小市值冷静期] 卖出货基失败: %s' % str(e))

        g.in_cooldown_small_cap = False
        return

    # 冷静期内清空股票
    sold_codes = []
    for code, pos in list(context.portfolio.positions.items()):
        if code == g.money_fund_small_cap:
            continue
        try:
            enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
            if enable_amount > 0:
                safe_sell(context, 'small_cap', code, enable_amount)
                sold_codes.append(code)
        except Exception as e:
            log.error('[小市值冷静期] 卖出失败 %s: %s' % (code, str(e)))

    # 买入货币基金
    cash = context.portfolio.cash
    if cash >= 10000:
        try:
            safe_buy_value(context, 'small_cap', g.money_fund_small_cap, cash)
        except Exception as e:
            log.error('[小市值冷静期] 买入货基失败: %s' % str(e))

    if sold_codes:
        log.info("[小市值冷静期] 天数%d/%d, 清仓%d只"
                 % (g.days_since_sell_small_cap, g.cooldown_days_small_cap, len(sold_codes)))


def _execute_cooldown_clear_small_cap(context, data):
    """
    执行冷静期清仓（v2.1修复）

    [v2.1修复] 只卖出小市值策略虚拟持仓中的股票
    - 遍历虚拟持仓而非真实持仓，避免误卖ETF策略持仓
    """
    log.info("[小市值冷静期清仓]")

    # [v2.1修复] 只清仓小市值策略的虚拟持仓，不影响ETF策略
    strat = g.strategies['small_cap']
    virtual_positions = strat['positions'].copy()

    for code, virtual_amt in virtual_positions.items():
        # 获取真实可用数量
        try:
            pos = context.portfolio.positions.get(code)
            if pos and pos.amount > 0:
                enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
                if enable_amount > 0:
                    safe_sell(context, 'small_cap', code, min(virtual_amt, enable_amount))
        except Exception as e:
            log.error("[冷静期清仓] %s 失败: %s" % (code, str(e)))

    # [v2.6] 使用固定份额计算剩余份额
    quota = g.strategy_quota.get('small_cap', 0)
    used = g.strategy_used.get('small_cap', 0)
    strategy_remaining = quota - used

    if strategy_remaining > 0:
        try:
            safe_buy_value(context, 'small_cap', g.money_fund_small_cap, strategy_remaining)
            log.info("[冷静期清仓] 买入货基 %.2f（策略剩余份额=%.0f%%）" % (strategy_remaining, quota / g.initial_capital * 100))
        except Exception as e:
            log.error("[冷静期清仓] 买入货基失败: %s" % str(e))


def _execute_empty_month_clear_small_cap(context, data):
    """
    执行空仓月清仓（v2.1修复）

    [v2.1修复] 只卖出小市值策略虚拟持仓中的股票
    - 遍历虚拟持仓而非真实持仓，避免误卖ETF策略持仓
    - ETF持仓不在小市值虚拟持仓中，不会被触及
    """
    log.info("[小市值空仓月清仓]")

    # [v2.1修复] 只清仓小市值策略的虚拟持仓，不影响ETF策略
    strat = g.strategies['small_cap']
    virtual_positions = strat['positions'].copy()

    for code, virtual_amt in virtual_positions.items():
        # 跳过货币基金
        if code == g.money_fund_small_cap:
            continue
        # 获取真实可用数量
        try:
            pos = context.portfolio.positions.get(code)
            if pos and pos.amount > 0:
                enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
                if enable_amount > 0:
                    safe_sell(context, 'small_cap', code, min(virtual_amt, enable_amount))
        except Exception as e:
            log.error("[空仓月清仓] %s 失败: %s" % (code, str(e)))

    # [v2.6] 使用固定份额计算剩余份额
    quota = g.strategy_quota.get('small_cap', 0)
    used = g.strategy_used.get('small_cap', 0)
    strategy_remaining = quota - used

    if strategy_remaining > 0:
        try:
            safe_buy_value(context, 'small_cap', g.money_fund_small_cap, strategy_remaining)
            log.info("[空仓月清仓] 买入货基 %.2f（策略剩余份额=%.0f%%）" % (strategy_remaining, quota / g.initial_capital * 100))
        except Exception as e:
            log.error("[空仓月清仓] 买入货基失败: %s" % str(e))


def _get_trade_stocks_small_cap(context, data, mode='sell'):
    """获取小市值交易股票列表"""
    if g.df2_small_cap is None or g.df2_small_cap.empty:
        return []

    df = g.df2_small_cap.copy()

    # 获取昨日收盘价
    stock_codes = df.index.tolist()
    try:
        his = get_history(1, frequency='1d', field='close',
                           security_list=stock_codes, fq='pre', include=False, is_dict=True)
    except:
        return []

    # 计算当前市值
    for code in stock_codes:
        try:
            if his is None or code not in his:
                continue

            yclose = float(his[code]['close'][-1])
            if yclose <= 0:
                continue

            try:
                px = data[code].price if code in data else yclose
            except:
                px = yclose

            if px <= 0:
                continue

            scale = px / yclose
            df.loc[code, 'curr_float_value'] = df.loc[code, 'float_value'] * scale
        except:
            pass

    df = df.dropna(subset=['curr_float_value'])
    if df.empty:
        return []

    # 按市值排序
    df = df.sort_values(by='curr_float_value', ascending=True)
    stocks = df.head(g.screen_stock_count_small_cap).index.tolist()

    # 涨停过滤
    try:
        lim = _limit_flags_today_small_cap(context, stocks)
        up_limit_stock = set(lim['up_limit'])
        stocks = [s for s in stocks if s not in up_limit_stock]
    except:
        pass

    # 已持仓中涨停的保留
    hold_codes = list(context.portfolio.positions.keys())
    try:
        lim_hold = _limit_flags_today_small_cap(context, hold_codes)
        hold_up = set(lim_hold['up_limit'])
    except:
        hold_up = set()

    # 返回数量
    if mode == 'sell':
        need_num = max(0, g.down_stock_count_small_cap - len(hold_up))
    else:
        need_num = max(0, g.buy_stock_count_small_cap - len(hold_up))

    return list(hold_up) + stocks[:need_num]


def _limit_flags_today_small_cap(context, codes):
    """判断涨停"""
    if not codes:
        return {'up_limit': [], 'down_limit': []}

    up, down = [], []
    for s in codes:
        try:
            limit_info = check_limit(s)
            if limit_info and s in limit_info:
                if limit_info[s] == 1:
                    up.append(s)
                elif limit_info[s] == -1:
                    down.append(s)
        except:
            pass

    return {'up_limit': up, 'down_limit': down}


# ============================================================
#                    盘后处理
# ============================================================

def after_trading_end(context, data):
    """
    盘后处理 - 输出双策略状态（按比例动态隔离）

    【输出】
    1. ETF策略：持仓、策略资产（按比例计算）
    2. 小市值策略：持仓、策略资产（按比例计算）
    3. 总账户：总资产、现金
    """
    log.info("=" * 50)
    log.info("=== 盘后状态 ===")

    positions = context.portfolio.positions
    hold_count = len([p for p in positions.values() if p.amount > 0])
    total_value = context.portfolio.portfolio_value if hasattr(context.portfolio, 'portfolio_value') else context.portfolio.total_value
    cash = context.portfolio.cash

    log.info("[总账户] 持仓%d只, 总资产%.2f, 现金%.2f" % (hold_count, total_value, cash))

    # ETF策略状态（按比例动态计算）
    if g.capital_ratio_etf > 0:
        etf_strat = g.strategies['etf_rotation']
        etf_hold = {code: amt for code, amt in etf_strat['positions'].items() if amt > 0}

        # 计算ETF策略资产
        etf_hold_value = 0.0
        for code, amt in etf_hold.items():
            try:
                price = _get_latest_price(code)
                if price and price > 0:
                    etf_hold_value += amt * price
            except:
                pass

        etf_strategy_cash = cash * g.capital_ratio_etf
        etf_strategy_assets = etf_hold_value + etf_strategy_cash

        log.info("[ETF策略] 策略资产%.2f = 持仓%.2f + 现金%.2f (%.0f%%)"
                 % (etf_strategy_assets, etf_hold_value, etf_strategy_cash, g.capital_ratio_etf * 100))
        log.info("[ETF策略] 虚拟持仓: %s" % (etf_hold))

    # 小市值策略状态（按比例动态计算）
    if g.capital_ratio_small_cap > 0:
        sc_strat = g.strategies['small_cap']
        sc_hold = {code: amt for code, amt in sc_strat['positions'].items() if amt > 0}

        # 计算小市值策略持仓市值（排除货币基金）
        sc_hold_value = 0.0
        for code, v_amt in sc_hold.items():
            try:
                price = _get_latest_price(code)
                if price and price > 0:
                    sc_hold_value += v_amt * price

                    # [DEBUG] 对比真实持仓
                    real_pos = get_position(code)
                    real_amt = real_pos.amount if real_pos else 0
                    if v_amt != real_amt:
                        log.info('[DEBUG][持仓差异] %s: 虚拟=%d, 真实=%d'
                                 % (code, v_amt, real_amt))
            except:
                pass

        cooldown_status = "冷静期" if g.in_cooldown_small_cap else "正常"
        sc_strategy_cash = cash * g.capital_ratio_small_cap
        sc_strategy_assets = sc_hold_value + sc_strategy_cash

        log.info("[小市值策略] 状态: %s, 策略资产%.2f = 持仓%.2f + 现金%.2f (%.0f%%)"
                 % (cooldown_status, sc_strategy_assets, sc_hold_value, sc_strategy_cash, g.capital_ratio_small_cap * 100))
        log.info("[小市值策略] 虚拟持仓: %s" % (sc_hold))

    log.info("=" * 50)
