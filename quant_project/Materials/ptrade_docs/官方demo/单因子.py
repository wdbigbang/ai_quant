"""
策略名称：
单因子日线交易策略
策略流程：
盘前将中小板成分股中st、停牌、退市的股票过滤得到股票池
盘中：
1、通过极值处理、标准化处理、市值中性化处理
2、因子排序获得股票池
3、动态平衡仓位
注意事项：
策略中调用的order_target_value接口的使用有场景限制，回测可以正常使用，交易谨慎使用。
回测场景下撮合是引擎计算的，因此成交之后持仓信息的更新是瞬时的，但交易场景下信息的更新依赖于柜台数据
的返回，无法做到瞬时同步，可能造成重复下单。详细原因请看帮助文档。
"""
import pandas as pd
import numpy as np
import statsmodels.api as sm
import math
from decimal import Decimal


# 初始化处理
def initialize(context):
    g.factor = 'roe'
    g.factor_params_info = {
        'roe': ['profit_ability', 'roe', False],  # 净资产收益率,最后布尔值为排序方式
        'operating_revenue_grow_rate': ['growth_ability', 'operating_revenue_grow_rate', False],
        # 营收增速
        'np_parent_company_cut_yoy': ['growth_ability', 'np_parent_company_cut_yoy', False],
        # 扣非净利润增速
    }
    # 初始化此策略
    set_params()  # 设置策参数
    set_variables()  # 设置中间变量
    if not is_trade():
        set_backtest()  # 设置回测条件


# 设置策参数
def set_params():
    g.tc = 15  # 调仓频率
    g.yb = 63  # 样本长度
    g.N = 20  # 持仓数目
    g.NoF = 3  # 三因子模型
    g.percent = 0.10


# 设置中间变量
def set_variables():
    g.days = 0  # 记录连续回测天数
    g.rf = 0.04  # 无风险利率
    g.is_trade = False  # 当天是否交易
    g.every_stock = 0


# 设置回测条件
def set_backtest():
    set_limit_mode('UNLIMITED')


# 盘前处理
def before_trading_start(context, data):
    g.current_date = context.blotter.current_dt.strftime("%Y%m%d")
    # g.all_stocks = get_index_stocks('000906.XBHS', g.current_date)
    g.all_stocks = get_index_stocks('000300.XBHS', g.current_date)
    if g.days % g.tc == 0:
        # 每g.tc天，交易一次行
        g.is_trade = True
        # 将ST、停牌、退市三种状态的股票剔除当日的股票池
        g.all_stocks = filter_stock_by_status(g.all_stocks, filter_type=["ST", "HALT", "DELISTING"], query_date=None)
    g.days += 1


# 每天交易时要做的事情
def handle_data(context, data):
    if g.is_trade:
        stock_sort = get_stocks(g.all_stocks, str(get_trading_day(-1)), g.factor)
        # 把涨停状态的股票剔除
        up_limit_stock = get_limit_stock(context, stock_sort)['up_limit']
        stock_sort = [stock for stock in stock_sort if stock not in up_limit_stock]
        position_list = get_position_list(context)
        # 持仓中跌停的股票不做卖出
        limit_info = get_limit_stock(context, position_list)
        hold_down_limit_stock = limit_info['down_limit']
        log.info('持仓跌停股：%s' % hold_down_limit_stock)
        # 持仓中除了不处于前g.N且跌停不能卖的股票进行卖出
        sell_stocks = list(set(position_list) - set(stock_sort[:g.N]) - set(hold_down_limit_stock))
        # 对不在换仓列表中且飞跌停股的股票进行卖出操作
        order_stock_sell(context, data, sell_stocks)
        # 获取仍在持仓中的股票
        position_list = get_position_list(context)
        # 获取调仓买入的股票
        buy_stocks = [stock for stock in stock_sort if stock not in position_list][:(g.N - len(position_list))]
        # 仓位动态平衡的股票
        balance_stocks = list(set(buy_stocks + position_list) - set(hold_down_limit_stock))
        log.info('balance_stocks%s' % len(balance_stocks))
        g.every_stock = context.portfolio.portfolio_value / g.N
        log.info('g.every_stock%s' % g.every_stock)
        order_stock_balance(context, data, balance_stocks)
        order_stock_balance(context, data, balance_stocks)
    g.is_trade = False


# 不在换仓目标中且没有跌停的股票进行清仓操作
def order_stock_sell(context, data, sell_stocks):
    # 对于不需要持仓的股票，全仓卖出
    for stock in sell_stocks:
        stock_sell = stock
        order_target_value(stock_sell, 0)


# 非跌停的换仓目标股进行仓位再平衡
def order_stock_balance(context, data, balance_stocks):
    for stock in balance_stocks:
        order_target_value(stock, g.every_stock)


# 获取拟持仓股票池
def get_stocks(stocks, date, factor):
    sort_type = g.factor_params_info[factor][-1]
    df = get_factor_values(stocks, factor, date, g.factor_params_info)
    df.dropna(inplace=True)
    if df.empty:
        print('%s数据获取失败，选股失败' % factor)
        return list()
    # 3倍标准差去极值
    df = winsorize(df, factor, std=3, have_negative=True)
    # z标准化
    df = standardize(df, factor, ty=2)
    # 市值中性化
    market_cap_df = get_fundamentals(stocks, 'valuation', fields='total_value', date=date)
    market_cap_df.dropna(inplace=True)
    if market_cap_df.empty:
        print('市值数据获取失败，选股失败')
        return list()
    market_cap_df = market_cap_df[['total_value']]
    # 中性化处理
    df = neutralization(df, factor, market_cap_df)
    df = df.sort_values(by=factor, ascending=sort_type)
    return list(df.head(int(len(df) * g.percent)).index)


# 获取因子值
def get_factor_values(stock_list, factor, date, factor_params_info):
    """
    获取因子值方法
    入参：
    1、股票池：stock_list
    2、因子名称：factor
    3、计算日期：date
    4、因子数据获取需要维护的信息（因子名称、表名、字段名）
    """
    data = get_fundamentals(stock_list, table=factor_params_info[factor][0], fields=factor_params_info[factor][1],
                            date=date, is_dataframe=True)
    factor_info = {}
    for stock in stock_list.copy():
        if stock not in data.index:
            continue
        factor_info[stock] = data.loc[stock, factor_params_info[factor][1]]
    if factor_info == {}:
        return pd.DataFrame()
    factor_df = pd.DataFrame.from_dict(factor_info, orient='index')
    factor_df.columns = [factor_params_info[factor][1]]
    return factor_df


# 保留小数点两位
def replace(x):
    x = Decimal(x)
    x = float(str(round(x, 2)))
    return x


# 生成昨日持仓股票列表
def get_position_list(context):
    position_last_list = [
        position.sid
        for position in context.portfolio.positions.values()
        if position.amount != 0
    ]
    return position_last_list


# 日级别回测获取持仓中不能卖出的股票(涨停就不卖出)
def get_limit_stock(context, stock_list):
    out_info = {'up_limit': [], 'down_limit': []}
    for stock in stock_list:
        limit_status = check_limit(stock)[stock]
        if limit_status == 1:
            out_info['up_limit'].append(stock)
        elif limit_status == -1:
            out_info['down_limit'].append(stock)
    return out_info


# 去极值函数（3倍标准差去极值）
def winsorize(factor_data, factor, std=3, have_negative=True):
    """
    去极值函数
    factor:以股票code为index，因子值为value的Series
    std为几倍的标准差，have_negative 为布尔值，是否包括负值
    输出Series
    """
    r = factor_data[factor]
    if not have_negative:
        r = r[r >= 0]
    # 取极值
    edge_up = r.mean() + std * r.std()
    edge_low = r.mean() - std * r.std()
    r[r > edge_up] = edge_up
    r[r < edge_low] = edge_low
    r = pd.DataFrame(r)
    return r


# z－score标准化函数：
def standardize(factor_data, factor, ty=2):
    """
    s为Series数据
    ty为标准化类型:1 MinMax,2 Standard,3 maxabs
    """
    temp = factor_data[factor]
    re = 0
    if int(ty) == 1:
        re = (temp - temp.min()) / (temp.max() - temp.min())
    elif ty == 2:
        re = (temp - temp.mean()) / temp.std()
    elif ty == 3:
        re = temp / 10 ** np.ceil(np.log10(temp.abs().max()))
    return pd.DataFrame(re)


# 市值中性化函数
def neutralization(data_factor, factor, data_market_cap):
    data_market_cap['total_value2'] = 0
    data_market_cap['total_value2'] = data_market_cap['total_value'].apply(lambda a: math.log(a))
    df = pd.concat([data_factor, data_market_cap], axis=1, join='inner')
    y = df[factor]
    x = df['total_value2']
    result = sm.OLS(y, x).fit()
    result = pd.DataFrame(result.resid)
    result.columns = [g.factor]
    return result