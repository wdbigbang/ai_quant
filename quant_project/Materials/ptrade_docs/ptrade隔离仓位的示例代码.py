# ============================================================
# PTrade 单账户多策略隔离模块
# 每个子策略独立维护虚拟资金与虚拟持仓，互不干扰
# ============================================================

def initialize(context):
    g.security = '600570.SS'
    set_universe(g.security)

    # ----------------------------------------------------------
    # 子策略配置：每个策略有唯一名称 + 独立资金上限（元）
    # 可按需增减策略条目
    # ----------------------------------------------------------
    strategy_configs = [
        {'name': 'strategy_A', 'capital': 100000.0},
        {'name': 'strategy_B', 'capital':  50000.0},
    ]

    # ----------------------------------------------------------
    # 初始化全局策略注册表
    # g.strategies 结构：
    #   {
    #     'strategy_A': {
    #         'capital':       100000.0,   # 初始资金上限
    #         'cash':          100000.0,   # 当前虚拟可用资金
    #         'positions': {               # 虚拟持仓 {code: amount}
    #             '600570.SS': 0,
    #         }
    #     },
    #     ...
    #   }
    # ----------------------------------------------------------
    g.strategies = {}
    for cfg in strategy_configs:
        g.strategies[cfg['name']] = {
            'capital':   cfg['capital'],
            'cash':      cfg['capital'],
            'positions': {},
        }

    log.info('策略隔离模块初始化完成，已注册策略: %s' % list(g.strategies.keys()))


# ============================================================
# 工具函数：获取当前最新价（回测/交易通用）
# ============================================================
def _get_latest_price(security):
    """
    通过 get_history 获取最近一根已收盘 K 线的收盘价，
    避免读取未闭合 K 线造成未来信息。
    """
    df = get_history(2, '1d', 'close', security_list=security, fq=None, include=False)
    if df is None or df.empty:
        log.error('获取 %s 价格失败' % security)
        return None
    return float(df['close'].iloc[-1])


# ============================================================
# safe_buy：子策略安全买入
# 参数：
#   strategy_name  - 子策略名称（必须已在 g.strategies 中注册）
#   security       - 标的代码，如 '600570.SS'
#   amount         - 期望买入股数（会自动取整到 100 的倍数）
#   limit_price    - 限价，None 表示使用最新价
# 返回：实际委托的 order_id 或 None
# ============================================================
def safe_buy(strategy_name, security, amount, limit_price=None):
    if strategy_name not in g.strategies:
        log.error('safe_buy: 未知策略 %s' % strategy_name)
        return None

    strat = g.strategies[strategy_name]

    # 取整到 100 股
    amount = int(amount / 100) * 100
    if amount <= 0:
        log.warning('[%s] safe_buy: 买入数量不足 100 股，跳过' % strategy_name)
        return None

    # 确定委托价格
    price = limit_price
    if price is None:
        price = _get_latest_price(security)
        if price is None:
            return None

    # 估算所需资金（含一定缓冲，避免因滑点不足）
    estimated_cost = price * amount * 1.001

    # 检查虚拟资金是否充足
    if strat['cash'] < estimated_cost:
        log.warning(
            '[%s] safe_buy: 虚拟资金不足，需要 %.2f，剩余 %.2f，跳过'
            % (strategy_name, estimated_cost, strat['cash'])
        )
        return None

    # 检查真实账户资金是否充足
    real_cash = context.portfolio.cash
    if real_cash < estimated_cost:
        log.warning(
            '[%s] safe_buy: 真实账户资金不足，需要 %.2f，真实剩余 %.2f，跳过'
            % (strategy_name, estimated_cost, real_cash)
        )
        return None

    # 先扣除虚拟资金（预扣，防止并发超买）
    strat['cash'] -= estimated_cost

    # 真实下单
    order_id = order(security, amount, limit_price=limit_price)

    if order_id is None:
        # 下单失败，退还虚拟资金
        strat['cash'] += estimated_cost
        log.error('[%s] safe_buy: 下单失败，已退还虚拟资金' % strategy_name)
        return None

    # 更新虚拟持仓
    strat['positions'][security] = strat['positions'].get(security, 0) + amount

    log.info(
        '[%s] safe_buy 成功: %s x %d 股，委托价 %.3f，虚拟剩余资金 %.2f'
        % (strategy_name, security, amount, price, strat['cash'])
    )
    return order_id


# ============================================================
# safe_sell：子策略安全卖出
# 参数：
#   strategy_name  - 子策略名称
#   security       - 标的代码
#   amount         - 期望卖出股数；传入 None 表示清空该策略虚拟持仓
#   limit_price    - 限价，None 表示使用最新价
# 返回：实际委托的 order_id 或 None
# ============================================================
def safe_sell(strategy_name, security, amount, limit_price=None):
    if strategy_name not in g.strategies:
        log.error('safe_sell: 未知策略 %s' % strategy_name)
        return None

    strat = g.strategies[strategy_name]

    # 该策略的虚拟持仓
    virtual_amount = strat['positions'].get(security, 0)
    if virtual_amount <= 0:
        log.warning('[%s] safe_sell: 该策略无 %s 虚拟持仓，跳过' % (strategy_name, security))
        return None

    # 确定期望卖出数量
    if amount is None:
        amount = virtual_amount
    amount = int(amount / 100) * 100
    if amount <= 0:
        log.warning('[%s] safe_sell: 卖出数量不足 100 股，跳过' % strategy_name)
        return None

    # 不超过本策略虚拟持仓
    amount = min(amount, virtual_amount)

    # 获取真实持仓数量（可用数量）
    real_position = get_position(security)
    real_enable = real_position.enable_amount if real_position else 0

    # 取 min(真实可用, 虚拟持仓) 避免超卖
    safe_amount = min(amount, real_enable)
    safe_amount = int(safe_amount / 100) * 100

    if safe_amount <= 0:
        log.warning(
            '[%s] safe_sell: 真实可用持仓不足（真实可用=%d，虚拟=%d），跳过'
            % (strategy_name, real_enable, virtual_amount)
        )
        return None

    # 真实下单（卖出为负数）
    order_id = order(security, -safe_amount, limit_price=limit_price)

    if order_id is None:
        log.error('[%s] safe_sell: 下单失败' % strategy_name)
        return None

    # 更新虚拟持仓
    strat['positions'][security] = virtual_amount - safe_amount
    if strat['positions'][security] <= 0:
        del strat['positions'][security]

    # 回收虚拟资金（按最新价估算）
    price = limit_price
    if price is None:
        price = _get_latest_price(security)
    if price is not None:
        recovered = price * safe_amount * 0.999  # 扣除估算手续费
        strat['cash'] += recovered
        # 虚拟资金不超过初始上限
        strat['cash'] = min(strat['cash'], strat['capital'])

    log.info(
        '[%s] safe_sell 成功: %s x %d 股，虚拟剩余持仓 %d，虚拟剩余资金 %.2f'
        % (
            strategy_name,
            security,
            safe_amount,
            strat['positions'].get(security, 0),
            strat['cash'],
        )
    )
    return order_id


# ============================================================
# 打印所有子策略当前状态（调试用）
# ============================================================
def print_strategy_status():
    for name, strat in g.strategies.items():
        log.info(
            '[状态] %s | 虚拟资金: %.2f / %.2f | 虚拟持仓: %s'
            % (name, strat['cash'], strat['capital'], strat['positions'])
        )


# ============================================================
# handle_data：示例逻辑
# strategy_A：简单均线策略
# strategy_B：固定周期买卖示例
# ============================================================
def handle_data(context, data):
    security = g.security

    # ---------- strategy_A：5日均线 vs 10日均线 ----------
    df = get_history(20, '1d', 'close', security_list=security, fq=None, include=False)
    if df is not None and not df.empty:
        close = df['close']
        ma5  = close[-5:].mean()
        ma10 = close[-10:].mean()

        virtual_pos_A = g.strategies['strategy_A']['positions'].get(security, 0)

        if ma5 > ma10 and virtual_pos_A == 0:
            # 金叉买入：用 strategy_A 虚拟资金的 50% 买入
            cash_A = g.strategies['strategy_A']['cash']
            price  = float(close.iloc[-1])
            if price > 0:
                target_amount = int((cash_A * 0.5) / price / 100) * 100
                safe_buy('strategy_A', security, target_amount)

        elif ma5 < ma10 and virtual_pos_A > 0:
            # 死叉卖出：清空 strategy_A 持仓
            safe_sell('strategy_A', security, None)

    # ---------- strategy_B：每隔 20 个交易周期买卖一次 ----------
    if not hasattr(g, 'bar_count'):
        g.bar_count = 0
    g.bar_count += 1

    virtual_pos_B = g.strategies['strategy_B']['positions'].get(security, 0)

    if g.bar_count % 20 == 1 and virtual_pos_B == 0:
        # 每 20 根 K 线买入一次，固定 200 股
        safe_buy('strategy_B', security, 200)

    elif g.bar_count % 20 == 11 and virtual_pos_B > 0:
        # 持有 10 根 K 线后卖出
        safe_sell('strategy_B', security, None)

    # 每 10 根 K 线打印一次状态
    if g.bar_count % 10 == 0:
        print_strategy_status()