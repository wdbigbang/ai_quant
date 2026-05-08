"""
策略名称：
单标的日内交易策略
运行周期:
分钟
策略流程：
盘中10点后每隔5分钟进行一次RSI短周期与长周期多空共振的判断，决定做正T还是反T；
盘中再按照盈利比例进行头寸恢复或者收盘前清算头寸恢复
注意事项：
策略中调用的order_target接口的使用有场景限制，回测可以正常使用，交易谨慎使用。
回测场景下撮合是引擎计算的，因此成交之后持仓信息的更新是瞬时的，但交易场景下信息的更新依赖于柜台数据
的返回，无法做到瞬时同步，可能造成重复下单。详细原因请看帮助文档。
"""
# 导入函数库

import numpy as np


# 初始化此策略
def initialize(context):
    # 设置我们要操作的股票池, 这里我们只操作一支股票
    g.ini_buy_flag = False  # 买底仓开关
    g.amount = 100  # 1份标准交易头寸
    g.rate = 1  # 做T涨跌幅，1就是1%
    g.L = 50  # 长周期RSI阈值
    g.S = 80  # 短周期RSI阈值
    g.security = '510500.SS'
    if not is_trade():
        set_limit_mode('UNLIMITED')


# 盘前处理
def before_trading_start(context, data):
    g.B_T_flag = False  # 做正T开关（先买后卖）
    g.S_T_flag = False  # 做反T开关（先卖后买）
    g.first_buy_flag = False
    g.second_buy_flag = False
    g.handle_data_flag = True
    current_date = context.blotter.current_dt.strftime('%Y-%m-%d')
    # 2013-04-01前510500.SS回测由于数据不足，不执行。可按照标的更改允许回测时间
    if current_date < '2013-04-01':
        g.trade_flag = False
    else:
        g.trade_flag = True


# 盘中处理
def handle_data(context, data):
    if not g.trade_flag:
        return
    # 盘中交易开关（一天只做一次T）
    if not g.handle_data_flag:
        return
    k_num = get_current_kline_count()
    if not g.ini_buy_flag:
        order(g.security, g.amount)
        g.ini_buy_flag = True
        g.handle_data_flag = False
    if k_num <= 30:
        return
    # 每个5分钟整点进行做T判断
    if k_num % 5 == 0:
        # 获取5分钟K线数据
        h = get_history(100, '5m', field=['close', 'volume'], security_list=g.security,
                        fq='dypre', include=True, is_dict=True)
        close_array_5m = h[g.security]['close']
        # 合成15分钟K线数据
        h = get_history(100, '15m', field=['close', 'volume'], security_list=g.security,
                        fq='dypre', include=False, is_dict=True)
        close_array_15m = h[g.security]['close']
        current_price = data[g.security].close
        close_array_15m = np.concatenate((close_array_15m, np.array(list([current_price]))), axis=0)
        if close_array_5m.ndim != 0 and close_array_15m.ndim != 0:
            # 获取5分钟、15分钟RSI
            rsi_5m = get_rsi(close_array_5m, 11)[-1]
            rsi_15m = get_rsi(close_array_15m, 11)[-1]
            # 做T条件判断
            if rsi_15m > g.L and rsi_5m > g.S:
                if get_position(g.security).enable_amount == g.amount and not g.B_T_flag:
                    order_id = order(g.security, g.amount)
                    if order_id is not None:
                        log.info('日内看多做正T')
                        g.B_T_flag = True
                        g.B_T_cost = data[g.security].price
            if rsi_15m < 100 - g.L and rsi_5m < 100 - g.S:
                if get_position(g.security).enable_amount == g.amount and not g.S_T_flag:
                    order_id = order(g.security, -g.amount)
                    if order_id is not None:
                        log.info('日内看空做反T')
                        g.S_T_flag = True
                        g.S_T_cost = data[g.security].price
    if g.B_T_flag:
        if data[g.security].price >= g.B_T_cost * (1 + g.rate / 100):
            order_id = order(g.security, -g.amount)
            if order_id is not None:
                log.info('做正T后恢复头寸')
                g.B_T_flag = False
    if g.S_T_flag:
        if data[g.security].price <= g.S_T_cost * (1 - g.rate / 100):
            order_id = order(g.security, g.amount)
            if order_id is not None:
                log.info('做反T后恢复头寸')
                g.S_T_flag = False
    # 收盘前多次尝试将持仓恢复到开盘持有量
    if k_num >= 238:
        log.info('收盘前多次尝试将持仓恢复到开盘持有量')
        order_id = order_target(g.security, g.amount)
        if order_id is not None:
            log.info('收盘清算')


# 获取RSI数据
def get_rsi(array_list, periods=14):
    length = len(array_list)
    rsi_values = [np.nan] * length
    if length <= periods:
        return rsi_values
    up_avg = 0
    down_avg = 0

    first_t = array_list[:periods + 1]
    for i in range(1, len(first_t)):
        if first_t[i] >= first_t[i - 1]:
            up_avg += first_t[i] - first_t[i - 1]
        else:
            down_avg += first_t[i - 1] - first_t[i]
    up_avg = up_avg / periods
    down_avg = down_avg / periods
    rs = up_avg / down_avg
    rsi_values[periods] = 100 - 100 / (1 + rs)

    for j in range(periods + 1, length):
        if array_list[j] >= array_list[j - 1]:
            up = array_list[j] - array_list[j - 1]
            down = 0
        else:
            up = 0
            down = array_list[j - 1] - array_list[j]
        up_avg = (up_avg * (periods - 1) + up) / periods
        down_avg = (down_avg * (periods - 1) + down) / periods
        rs = up_avg / down_avg
        rsi_values[j] = 100 - 100 / (1 + rs)
    return rsi_values