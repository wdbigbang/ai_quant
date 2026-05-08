"""
策略名称：
AROON指标策略
注意事项：
策略中调用的order_target接口的使用有场景限制，回测可以正常使用，交易谨慎使用。
回测场景下撮合是引擎计算的，因此成交之后持仓信息的更新是瞬时的，但交易场景下信息的更新依赖于柜台数据
的返回，无法做到瞬时同步，可能造成重复下单。详细原因请看帮助文档。
"""
import talib as ta


# 初始化
def initialize(context):
    g.stock = "000333.SZ"
    g.period = 20


# 每个交易日处理
def before_trading_start(context, data):
    current_date = context.blotter.current_dt.strftime('%Y-%m-%d')
    # 2013-10-01前回测由于数据不足，不执行。
    if current_date < '2013-10-01':
        g.trade_flag = False
    else:
        g.trade_flag = True


def handle_data(context, data):
    if not g.trade_flag:
        return
    log.info(g.stock + '当前持仓' + str(get_position(g.stock).amount))
    high = get_history(g.period * 2, frequency='1d', field='high', security_list=g.stock, fq='pre', is_dict=True)
    low = get_history(g.period * 2, frequency='1d', field='low', security_list=g.stock, fq='pre', is_dict=True)
    # 通过talib库计算AROON指标值   
    aroon_down, aroon_up = ta.AROON(high[g.stock]['high'], low[g.stock]['low'], g.period)
    aroon = aroon_up - aroon_down
    signal = 0
    if aroon_up[-2] < 70 <= aroon_up[-1] and aroon[-1] > 0:
        signal += 1
    if aroon_down[-2] < 70 <= aroon_down[-1] and aroon[-1] < 0:
        signal += -1
    if aroon_up[-2] > 50 >= aroon_up[-1] and aroon[-1] < 0:
        signal += -1
    if aroon_down[-2] > 50 >= aroon_down[-1] and aroon[-1] > 0:
        signal += 1
    if signal > 0 and get_position(g.stock).amount == 0:
        order_value(g.stock, context.portfolio.cash)
    if signal < 0 < get_position(g.stock).amount:
        order_target(g.stock, 0)