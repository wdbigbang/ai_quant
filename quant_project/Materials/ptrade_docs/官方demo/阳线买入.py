"""
策略名称：
阳线策略
注意事项：
策略中调用的order_target、order_target_value接口的使用有场景限制，回测可以正常使用，交易谨慎使用。
回测场景下撮合是引擎计算的，因此成交之后持仓信息的更新是瞬时的，但交易场景下信息的更新依赖于柜台数据
的返回，无法做到瞬时同步，可能造成重复下单。详细原因请看帮助文档。
"""
import numpy as np
from decimal import Decimal


def initialize(context):
    if is_trade():
        log.info('-----trade-------')
    else:
        set_fixed_slippage(0.0)
        set_slippage(slippage=0.01)
        set_limit_mode('UNLIMITED')
    g.before_start = False
    # 持仓数量
    g.hold_num = 10


def before_trading_start(context, data):
    g.current_date = context.blotter.current_dt.strftime("%Y%m%d")
    # 持仓股昨日最低价容器
    g.holds_pre_low_price = {}
    # 今日开盘价容器
    g.open_price_info = {}
    # 昨日持仓股
    g.position_list = []
    # 获取全市场股票，选最近10个交易日K线，判断个股形态：最近的一个阴K线之后没有阳线结构，符合形态且当天没有停牌的就加入股票池
    g.stock_list = get_Ashares()

    his_data_info = get_history(10, frequency='1d', field=['open', 'close', 'volume'],
                                security_list=g.stock_list, fq=None, include=False, is_dict=True)
    halt_status = get_stock_status(g.stock_list, 'HALT')
    g.buy_stocks = []
    for stock in g.stock_list.copy():
        # 停牌的过滤
        if halt_status[stock]:
            continue
        his_data = his_data_info[stock]
        his_data = np.array(list(filter(volume_filter, his_data)))
        if len(his_data) < 2:
            continue
        yinx_flag = False
        yangx_flag = False
        is_true = False
        for stock_data in reversed(his_data):
            if stock_data['close'] < stock_data['open']:
                yinx_flag = True
            if stock_data['close'] > stock_data['open']:
                yangx_flag = True
            if yinx_flag and not yangx_flag:
                is_true = True
                break
            if not yinx_flag and yangx_flag:
                is_true = False
                break
        if is_true:
            g.buy_stocks.append(stock)
    g.before_start = True
    g.first_handledata = False
    total_value = context.portfolio.portfolio_value
    g.cash = total_value / g.hold_num

    # 对持仓进行数据载入
    g.position_list = position_last_close_init(context)
    log.info(('盘前查询持仓股:', g.position_list))
    log.info(len(g.position_list))
    # 判断持仓股是否停牌，停牌的标的当日不做交易判断
    halt_status = get_stock_status(g.position_list, 'HALT')
    pre_low_data = get_history(1, '1d', 'low', security_list=g.position_list, fq='dypre', is_dict=True)
    for stock in g.position_list.copy():
        # 停牌的过滤
        if halt_status[stock]:
            g.position_list.remove(stock)
            continue
        # 非停牌持仓股获取昨日最低价
        g.holds_pre_low_price[stock] = pre_low_data[stock]['low'][0]


def handle_data(context, data):
    # 确保盘前处理已完成
    if not g.before_start:
        return
    g.K_num = get_current_kline_count()
    # 第一分钟处理
    if not g.first_handledata:
        # 回测场景持仓股及拟买股票池赋值开盘价
        if not is_trade():
            for stock in g.buy_stocks:
                g.open_price_info[stock] = data[stock].open
            for stock in g.position_list:
                g.open_price_info[stock] = data[stock].open
        g.first_handledata = True

    # 14:45之前持仓股如果符合最新价小于昨日最低价条件清仓
    if g.K_num < 225:
        if is_trade():
            for stock in g.position_list.copy():
                snapshot = get_snapshot(stock)
                if snapshot[stock]['last_px'] < g.holds_pre_low_price[stock]:
                    order_target(stock, 0)
                    g.position_list.remove(stock)
        else:
            for stock in g.position_list.copy():
                if data[stock].close < g.holds_pre_low_price[stock]:
                    order_target(stock, 0)
                    g.position_list.remove(stock)

    # 14:45分对非涨停状态的个股进行清仓
    if g.K_num == 225:
        for stock in g.position_list.copy():
            stock_flag = check_limit(stock)[stock]
            if stock_flag != 1:
                order_target(stock, 0)
                g.position_list.remove(stock)

    # 14:50分进行买入,校验当日实体阳线K线
    if g.K_num == 230:
        hold_list = position_last_close_init(context)
        if is_trade():
            count = 0
            for stock in g.buy_stocks:
                if count + len(hold_list) < g.hold_num and stock not in hold_list:
                    snapshot = get_snapshot(stock)
                    if snapshot[stock]['last_px'] > g.open_price_info[stock]:
                        order_target_value(stock, g.cash)
                        count += 1
        else:
            count = 0
            for stock in g.buy_stocks:
                if count + len(hold_list) < g.hold_num and stock not in hold_list:
                    if data[stock].close > g.open_price_info[stock]:
                        order_target_value(stock, g.cash)
                        count += 1


# 生成持仓股票列表
def position_last_close_init(context):
    position_last_list = []
    for stock in context.portfolio.positions:
        if context.portfolio.positions[stock].amount != 0:
            position_last_list.append(stock)
    return position_last_list


# 保留小数点两位
def replace(x):
    x = Decimal(x)
    x = float(str(round(x, 2)))
    return x


# 按成交量筛选停牌的数据
def volume_filter(data):
    if data['volume'] > 0:
        return data