# -*- coding: utf-8 -*-
def initialize(context):
    """
    策略初始化函数

    在回测开始时调用一次，用于设置策略参数、交易成本、定时任务等。

    Parameters:
    -----------
    context : Context
        聚宽策略上下文对象，包含账户信息、时间信息等
    """
    # 设置基准为沪深300指数，用于比较策略表现
    set_benchmark("000300.XSHG")
    
    # 设置要交易的股票代码（深交所平安银行）
    # 聚宽股票代码格式：6位数字.XSHE（深交所）或 XSHG（上交所）
    # g 是聚宽提供的全局变量对象，用于存储策略运行过程中的全局变量
    g.security = "000001.XSHE"

    # 设置定时任务：在每个交易日的每个时间片调用 market_open 函数
    # time='every_bar' 表示在回测的每个时间片都调用（日线回测即每天调用一次）
    # reference_security 参数用于指定参考证券，用于确定交易日历
    run_daily(market_open, time='9:30')
    run_daily(after_market_close, time='15:30')
    
    # 每周执行一次交易函数，-1表示每周最后一个交易日，10:31执行
    #run_weekly(market_open,-1, time='10:31')
    
    # 每月执行一次交易函数，1表示每月第一个交易日，10:31执行（已注释）
    #run_monthly(market_open,1, time='10:31')
    
    # 每日收盘后执行after_market_close函数，15:30执行
    #run_daily(after_market_close, time='15:30')
    
    # 设置滑点模型：PriceRelatedSlipPage表示按价格比例滑点，0.002表示0.2%的滑点
    # 滑点是实际成交价格与期望价格之间的差异，模拟真实交易中的价格冲击
    set_slippage(PriceRelatedSlippage(0.002), type='stock')
    
    # 设置订单成交量比例，0.5表示每次下单量不超过当日成交量的50%
    set_option('order_volume_ratio', 0.5)
    
    # 设置使用真实价格，而不是模拟价格
    set_option('use_real_price', True)
    
    # 设置避免未来数据，确保回测中不使用未来信息
    set_option('avoid_future_data', True)

    # 设置交易成本
    # OrderCost 参数说明：
    # - open_tax: 买入时的印花税（股票买入无印花税）
    # - close_tax: 卖出时的印花税（股票卖出 0.1%）
    # - open_commission: 买入时的佣金率（0.03%）
    # - close_commission: 卖出时的佣金率（0.03%）
    # - close_today_commission: 当日平仓的佣金率（股票无此费用）
    # - min_commission: 最低佣金（5 元）
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
                             open_commission=0.0003, close_commission=0.0003,
                             close_today_commission=0, min_commission=5), type='stock')


def market_open(context):
    """
    市场开盘交易函数（简单测试版本）
    
    这是一个简化的交易函数，用于测试基本的订单操作。
    逻辑：无持仓时买入1000股，有持仓时卖出800股。
    
    Args:
        context: 聚宽策略上下文对象，包含账户信息、时间信息等
    """
    # 检查是否持有目标股票
    # context.portfolio.positions 是持仓字典，key为股票代码
    if g.security not in context.portfolio.positions:
        # 无持仓时，按股数下单买入1000股
        # order函数：正数表示买入，负数表示卖出
        order(g.security, 1000)
    else:
        # 有持仓时，卖出800股
        order(g.security, -800)

def after_market_close(context):
    """
    收盘后处理函数（交易日志版本）
    
    在每个交易日收盘后调用，用于记录当天的交易详情。
    通过分析交易日志，可以回顾和验证策略的执行情况。
    
    Args:
        context: 聚宽策略上下文对象，包含账户信息、时间信息等
    """
    # 打印日志标记，便于在回测日志中定位
    log.info("收盘后函数执行")
    
    # 获取当日所有成交记录
    # get_trades() 返回一个字典，key为订单ID，value为交易对象
    # 只包含当天已成交的交易
    trades = get_trades()
    
    # 遍历所有成交记录，打印详细信息
    for _trade in trades.values():
        # _trade 对象包含以下主要属性：
        # - time: 成交时间
        # - order_id: 关联的订单ID
        # - price: 成交价格
        # - amount: 成交数量
        # - commission: 交易费用
        log.info(f"交易信息: {_trade} 成交时间: {_trade.time} 订单号 {_trade.order_id}")


def market_open_2(context):
    """
    市场开盘交易函数（订单对象调试版本）
    
    这个函数演示了如何检查订单对象的属性，包括：
    - 订单是否创建成功
    - 订单的状态（已提交、已成交、部分成交、已撤销等）
    - 交易费用、成交价格等信息
    
    Args:
        context: 聚宽策略上下文对象，包含账户信息、时间信息等
    """
    # 检查是否持有目标股票
    if g.security not in context.portfolio.positions:
        # 按股数下单买入100股
        # order函数返回一个订单对象，如果下单失败则返回None
        orders = order(g.security, 100)
        
        # 打印订单对象，便于调试查看
        print("买入订单: ", orders)
        
        # 检查订单是否创建成功
        if orders is None:
            # 订单创建失败的可能原因：
            # - 资金不足
            # - 股票停牌
            # - 交易时间不在交易时段
            # - 滑点设置导致无法成交
            print("创建订单失败 ")  
        else:
            # 订单对象包含以下主要属性：
            # - commission: 交易费用（佣金+印花税）
            # - is_buy: 是否为买单（True=买，False=卖）
            # - status: 订单状态（0=已提交，1=已成交，2=部分成交，3=已撤销）
            # - price: 平均成交价格
            # - amount: 订单数量
            # - filled: 已成交数量
            print(f"交易费用：{orders.commission}, 是否买单：{orders.is_buy}, 订单状态：{orders.status} 平均成交价：{orders.price}")
    else:
        # 有持仓时，卖出800股
        order(g.security, -800)

# debug - 这是一个调试用的交易函数，用于测试基本的买卖操作
def market_open_1(context):
    """
    市场开盘时的交易函数（调试版本）
    
    这个函数用于测试基本的买卖操作，不考虑任何技术指标，
    只是简单地根据是否持仓来决定买入或卖出。
    
    Args:
        context: 聚宽策略上下文对象，包含账户信息、时间信息等
    """
    # 注入资金10000元到账户，pindex=0表示第一个子账户（用于多账户策略）
    # inout_cash函数用于在回测过程中注入或提取资金，通常用于测试或调整资金
    inout_cash(10000, pindex = 0)
    
    # 打印并记录当前可用资金
    # context.portfolio.available_cash 表示当前可以用于交易的资金
    log.info("可用资金: {}".format(context.portfolio.available_cash))
    cash = context.portfolio.available_cash
    log.info("可用资金: {}".format(cash))
    
    # 检查当前是否持有目标股票
    # context.portfolio.positions 是一个字典，包含所有持仓股票的信息
    if g.security not in context.portfolio.positions:
        # 如果没有持有股票，则全仓买入
        # order_value 表示按金额下单，使用全部可用资金买入股票
        # 这种下单方式会根据可用资金和当前股价计算可买入的股数（100股的整数倍）
        order_value(g.security, cash)
        log.info("买入股票: {}".format(g.security))
    else:
        # 如果已经持有股票，则全部卖出
        # order_target 表示按数量下单，0表示清仓
        # 这种下单方式会将持仓数量调整到目标数量（这里是0，即全部卖出）
        order_target(g.security, 0)
        log.info("卖出股票: {}".format(g.security))

def after_market_close_0(context):
    """
    收盘后的处理函数
    
    这个函数在每个交易日收盘后调用，主要用于检查未成交订单并进行撤单处理，
    避免隔夜持仓风险。在实盘交易中，未成交的订单可能会在第二天开盘时以不利价格成交，
    因此通常会在收盘前撤销所有未成交订单。
    
    Args:
        context: 聚宽策略上下文对象，包含账户信息、时间信息等
    """
    # 获取所有未成交的订单
    # get_open_orders() 返回一个包含所有未成交订单的列表
    # 未成交订单是指已经提交但尚未完全成交的订单
    orders = get_open_orders()
    
    # 遍历并打印所有未成交订单
    # 这有助于在回测或实盘中监控订单状态
    for _order in orders:
        log.info("未成交订单: {}".format(_order))
    
    # 对未完成订单进行撤单
    # cancel_order 用于撤销指定的订单
    # 在收盘前撤销未成交订单是一种常见的风险控制措施
    for _order in orders:
        cancel_order(_order)
        log.info("已撤单: {}".format(_order))

    # 以下是一段被注释的代码，可能是另一种交易策略的测试代码
    # 这段代码实现了一个简单的买卖策略：
    # - 如果没有持有股票，买入1000股
    # - 如果已经持有股票，卖出800股
    # order函数直接按股数下单，正数表示买入，负数表示卖出
    """
    if g.security not in context.portfolio.positions:
        order(g.security, 1000)
    else:
        order(g.security, -800)
    """

def market_open_0(context):
    """
    基于5日均线的交易函数（原始版本）
    
    这个函数实现了基于5日均线的简单趋势跟踪策略：
    - 当价格上涨超过MA5的1%时买入
    - 当价格下跌超过MA5的1%时卖出
    
    这种策略的基本思想是：当价格突破均线时认为趋势开始，当价格跌破均线时认为趋势结束。
    1%的阈值是为了过滤掉小幅波动，避免频繁交易。
    
    Args:
        context: 聚宽策略上下文对象，包含账户信息、时间信息等
    """
    # 获取要交易的股票代码
    security = g.security

    # 获取过去 5 天的收盘价数据
    # attribute_history 是聚宽提供的历史数据获取函数
    # 参数说明：
    # - security: 股票代码
    # - count: 获取的天数（5 天）
    # - unit: 时间单位（'1d' 表示日线）
    # - fields: 要获取的字段（['close'] 表示收盘价）
    # 返回值：DataFrame，索引为日期，列为收盘价
    close_data = attribute_history(security=security, count=5, unit='1d', fields=['close'])

    # 计算 5 日移动平均线（MA5）
    # mean()函数计算收盘价的平均值，即5日均线值
    # 移动平均线是技术分析中最常用的指标之一，用于平滑价格波动，识别趋势方向
    MA5 = close_data['close'].mean()

    # 获取当前价格（最新一天的收盘价）
    # [-1]表示获取数组最后一个元素，即最新一天的收盘价
    # 在日线回测中，这通常表示前一交易日的收盘价
    current_price = close_data['close'][-1]

    # 获取可用资金
    # context.portfolio.available_cash 表示当前可以用于交易的资金
    # 这是账户中可以用于新开仓的资金，不包括已占用资金
    cash = context.portfolio.available_cash

    # 买入条件：当前价格 > MA5 × 1.01 且可用资金 > 当前价格
    # 1.01 表示价格上涨超过 MA5 的 1%，过滤掉小幅波动
    # 这个阈值可以根据策略需求调整，值越大交易越少，值越小交易越频繁
    # cash > current_price 确保有足够的资金买入至少 100 股（A股最小交易单位）
    if current_price > 1.01 * MA5 and cash > current_price:
        # 按金额下单：使用全部可用资金买入股票
        # order_value 是聚宽提供的下单函数之一，按金额下单
        # 参数说明：
        # - security: 股票代码
        # - cash: 买入金额（使用全部可用资金）
        # 系统会自动计算可买入的股数（100股的整数倍）
        order_value(security, cash)
        # 记录买入日志，便于回测后分析交易行为
        log.info("Buying {}".format(security))

    # 卖出条件：当前价格 < MA5 × 0.99 且持有股票可卖出
    # 0.99 表示价格下跌超过 MA5 的 1%
    # context.portfolio.positions[security].closeable_amount 表示当前持仓可卖出的数量
    # closeable_amount 是考虑了T+1交易规则后的可卖出数量（A股当天买入的股票不能当天卖出）
    elif current_price < 0.99 * MA5 and context.portfolio.positions[security].closeable_amount > 0:
        # 目标价值下单：将持仓价值设置为 0（即全部卖出）
        # order_target_value 是聚宽提供的另一种下单函数，按目标市值调整仓位
        # 参数说明：
        # - security: 股票代码
        # - 0: 目标持仓价值（0 表示清仓）
        # 这种下单方式会自动计算需要卖出多少股才能达到目标市值
        order_target_value(security, 0)
        # 记录卖出日志，便于回测后分析交易行为
        log.info("Selling {}".format(security))

    # 记录数据到回测结果中
    # record 函数用于记录自定义指标，这些指标会显示在回测结果图表中
    # 参数格式：record(指标名1=值1, 指标名2=值2, ...)
    # 这里记录了股票当前价格和5日均线值，便于在回测结果中观察
    # 通过这些指标，可以直观地看到买卖点与价格、均线的关系
    record(stock_price=current_price, MA5=MA5)