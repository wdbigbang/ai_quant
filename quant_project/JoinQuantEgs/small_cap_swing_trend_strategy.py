# 克隆自聚宽文章：https://www.joinquant.com/post/61055
# 标题：【年化87%低回撤】原创实盘小市值趋势波段策略
# 作者：liulijun

from jqdata import *
from jqfactor import *
import numpy as np
import pandas as pd
from datetime import time, date
from jqdata import finance

# 初始化函数
def initialize(context):
    # 开启防未来函数
    set_option('avoid_future_data', True)
    # 设定基准
    set_benchmark('399101.XSHE')
    # 用真实价格交易
    set_option('use_real_price', True)
    # 将滑点设置为0
    set_slippage(FixedSlippage(3 / 10000))
    # 设置交易成本万分之三
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=1 / 10000, close_commission=1 / 10000,
                             close_today_commission=0, min_commission=5), type='stock')
    # 过滤order中低于error级别的日志
    log.set_level('order', 'error')
    log.set_level('system', 'error')
    log.set_level('strategy', 'debug')
    # 初始化全局变量 bool
    g.trading_signal = True  # 是否为可交易日
    g.run_stoploss = True  # 是否进行止损
    g.filter_audit = False  # 是否筛选审计意见
    g.adjust_num = True  # 是否调整持仓数量
    # 全局变量list
    g.hold_list = []  # 当前持仓的全部股票
    g.yesterday_HL_list = []  # 记录持仓中昨日涨停的股票
    g.target_list = []
    g.pass_months= [1,4]  # 空仓的月份
    g.limitup_stocks = []  # 记录涨停的股票避免再次买入
    # 全局变量float/str
    g.min_mv = 10  # 股票最小市值要求
    g.max_mv = 100  # 股票最大市值要求
    g.stock_num = 5  # 持股数量

    g.stoploss_list = []  # 止损卖出列表
    g.other_sale = []  # 其他卖出列表
    g.stoploss_strategy = 5  # 联合止损策略
    g.stoploss_limit = 0.03  # 止损线
    g.stoploss_market = 0.03  # 市场趋势止损参数
    g.highest = 50  # 股票单价上限设置
    g.money_etf = '511880.XSHG'  # 空仓月份持有银华日利ETF
    # 设置交易运行时间
    run_daily(prepare_stock_list, '9:05')
    run_daily(trade_afternoon, time='14:00', reference_security='399101.XSHE')
    run_daily(stop_loss, time='10:00')
    run_daily(close_account, '14:50')
    run_weekly(weekly_adjustment, 2, '09:50')

# 准备股票池
def prepare_stock_list(context):
    g.limitup_stocks = []
    g.hold_list = list(context.portfolio.positions)
    # 获取昨日涨停列表
    if g.hold_list:
        df = get_price(g.hold_list, end_date=context.previous_date, frequency='daily',
                       fields=['close', 'high_limit', 'low_limit'], count=1, panel=False, fill_paused=False)
        df = df[df['close'] == df['high_limit']]
        g.yesterday_HL_list = df['code'].tolist()
    else:
        g.yesterday_HL_list = []
    # 判断今天是否为账户资金再平衡的日期
    old_signal = g.trading_signal
    g.trading_signal = today_is_between(context)
    # 记录信号变化
    if old_signal != g.trading_signal:
        log.info('交易信号变化: {} -> {} (日期: {})'.format(old_signal, g.trading_signal, context.current_dt.date()))

# 选股模块
def get_stock_list(context):
    final_list = []
    MKT_index = '399101.XSHE'
    initial_list = filter_stocks(context, get_index_stocks(MKT_index))
    
    q = query(
        valuation.code,
    ).filter(
        valuation.code.in_(initial_list),
        valuation.market_cap.between(g.min_mv, g.max_mv),
        income.np_parent_company_owners > 0,
        income.net_profit > 0,
        income.operating_revenue > 1e8
    ).order_by(valuation.market_cap.asc())
    df = get_fundamentals(q)
    
    if g.filter_audit:
        before_audit_filter = len(df)
        df['audit'] = df['code'].apply(lambda x: filter_audit(context, x))
        df_audit = df[df['audit'] == True]
        log.info('去除掉了存在审计问题的股票{}只'.format(len(df) - before_audit_filter))
    final_list = df['code'].tolist()

    return_list = []
    if final_list:
        stock_df = get_price(security=final_list, end_date=context.previous_date, frequency='daily', 
                            fields=['open', 'close', 'high', 'low', 'volume', 'money','high_limit','low_limit'], 
                            count=50, panel=False, fill_paused=True)
        result_df = band_trading(stock_df)
        result_df = result_df[result_df['time'] == context.previous_date]
        
        for stock in final_list:
            stock_df_tmp = result_df[result_df['code'] == stock]
            close = stock_df_tmp['close'].values[0]
            bug_status = stock_df_tmp['买'].values[0]
            high_limit = stock_df_tmp['high_limit'].values[0]
            low_limit = stock_df_tmp['low_limit'].values[0]
            if stock in g.hold_list or (close <= g.highest and bug_status == '买' and close != high_limit and close != low_limit):
                return_list.append(stock)
        return return_list
    else:
        log.info('无适合股票，买入ETF')
        return [g.money_etf]

# 波段交易函数
def band_trading(df):
    CLOSE = df['close']
    LOW = df['low']
    HIGH = df['high']
    N1 = 7
    N2 = 5
    N3 = 3
    ABC1 = (((HIGH + LOW) + (CLOSE * 2)) / 4)
    ABC3 = EMA(ABC1, N1)
    ABC4 = STD(ABC1, N1)
    ABC5 = ((ABC1 - ABC3) * 100) / ABC4
    ABC6 = EMA(ABC5, N2)
    RK7 = EMA(ABC6, N1)
    UP = (EMA(ABC6, 10) + (100 / 2)) - 5
    DOWN = EMA(UP, N3)
    ACB1 = EMA(DOWN, N3)
    ACB2 = EMA(ACB1, N3)
    ACB3 = EMA(ACB2, N3)
    ACB4 = EMA(ACB3, N3)
    
    df['柱子'] = IF(UP > REF(UP, 1), '红色', '蓝色')
    df['买'] = IF(AND(UP > REF(UP, 1), REF(UP, 1) < REF(UP, 2)), '买', None)
    df['卖'] = IF(AND(UP < REF(UP, 1), REF(UP, 1) > REF(UP, 2)), '卖', None)
    
    stats_list = []
    for buy, sell in zip(df['买'].tolist(), df['卖'].tolist()):
        if buy == '买':
            stats_list.append('买')
        elif sell == '卖':
            stats_list.append('卖')
        else:
            stats_list.append(None)
    df['stats'] = stats_list
    df['stats'] = df['stats'].fillna(method='ffill')

    return df

# 整体调整持仓
def weekly_adjustment(context):
    if g.trading_signal:
        if g.adjust_num:
            new_num = adjust_stock_num(context)
            g.stock_num = new_num
            log.info(f'持仓数量修改为{new_num}')
        g.target_list = get_stock_list(context)[:g.stock_num]
        log.info(str(g.target_list))

        sell_list = [stock for stock in g.hold_list if stock not in g.target_list and stock not in g.yesterday_HL_list]
        hold_list = [stock for stock in g.hold_list if stock in g.target_list or stock in g.yesterday_HL_list]
        log.info("卖出[%s]" % (str(sell_list)))
        log.info("已持有[%s]" % (str(hold_list)))

        for stock in sell_list:
            order_target_value(stock, 0)
        
        buy_list = [stock for stock in g.target_list if stock not in g.hold_list]
        if len(buy_list) < g.stock_num:
            print(f"当前出票少，代表市场不行，降低仓位")
            buy_security(context, buy_list, g.stock_num)
        else: 
            buy_security(context, buy_list, len(buy_list))
    else:
        buy_security(context, [g.money_etf], 1)
        log.info('该月份为空仓月份，持有银华日利ETF')

# 调整昨日涨停股票
def check_limit_up(context):
    now_time = context.current_dt
    if g.yesterday_HL_list != []:
        for stock in g.yesterday_HL_list:
            current_data = get_price(stock, end_date=now_time, frequency='1m', fields=['close', 'high_limit'],
                                     skip_paused=False, fq='pre', count=1, panel=False, fill_paused=True)
            if current_data.iloc[0, 0] < current_data.iloc[0, 1]:
                log.info("[%s]涨停打开，卖出" % (stock))
                order_target_value(stock, 0)
                g.other_sale.append(stock)
                g.limitup_stocks.append(stock)
            else:
                log.info("[%s]涨停，继续持有" % (stock))

# 检查剩余资金并买入
def check_remain_amount(context):
    addstock_num = len(g.other_sale)
    loss_num = len(g.stoploss_list)
    empty_num = addstock_num + loss_num

    g.hold_list = context.portfolio.positions
    if len(g.hold_list) < g.stock_num:
        num_stocks_to_buy = g.stock_num - len(g.hold_list)
        g.target_list = get_stock_list(context)[:g.stock_num]
        target_list = [stock for stock in g.target_list if stock not in g.limitup_stocks][:num_stocks_to_buy]
        log.info('有余额可用' + str(round((context.portfolio.cash), 2)) + '元。买入' + str(target_list))
        print(f"需要买入{num_stocks_to_buy}只股票")
        if len(target_list) < num_stocks_to_buy and len(target_list) > 0:
            print(f"当前出票较少，只买部分仓位")
            buy_security(context, target_list, g.stock_num)
        else:
            buy_security(context, target_list, len(target_list))

    g.stoploss_list = []
    g.other_sale = []

# 下午检查交易
def trade_afternoon(context):
    if g.trading_signal:
        check_limit_up(context)
        check_remain_amount(context)

# 止盈止损
def stop_loss(context):
    if g.run_stoploss:
        current_positions = context.portfolio.positions
        if g.stoploss_strategy == 1 or g.stoploss_strategy == 4 or g.stoploss_strategy == 5:
            for stock in current_positions.keys():
                price = current_positions[stock].price
                avg_cost = current_positions[stock].avg_cost
                if price >= avg_cost * 2:
                    order_target_value(stock, 0)
                    log.debug("收益100%止盈,卖出{}".format(stock))
                    g.other_sale.append(stock)
                elif price < avg_cost * (1 - g.stoploss_limit):
                    order_target_value(stock, 0)
                    log.debug("收益止损,卖出{}".format(stock))
                    g.stoploss_list.append(stock)

        if g.stoploss_strategy == 2 or g.stoploss_strategy == 4 or g.stoploss_strategy == 5:
            stock_df = get_price(security=get_index_stocks('399101.XSHE')
                                 , end_date=context.previous_date, frequency='daily'
                                 , fields=['close', 'open'], count=1, panel=False)
            down_ratio = (1 - stock_df['close'] / stock_df['open']).mean()
            if down_ratio >= g.stoploss_market:
                log.debug("大盘惨跌,平均降幅{:.2%}".format(down_ratio))
                for stock in current_positions.keys():
                    order_target_value(stock, 0)
                    g.stoploss_list.append(stock)

        if g.stoploss_strategy == 3 or g.stoploss_strategy == 5:
            stock_list_tmp = list(current_positions.keys())
            print(f"持仓股票：{stock_list_tmp}")
            if len(stock_list_tmp) > 0:
                stock_df = get_price(security=stock_list_tmp, end_date=context.previous_date, frequency='daily', 
                                    fields=['open', 'close', 'high', 'low', 'volume', 'money'], count=50, panel=False, fill_paused=True)
                result_df = band_trading(stock_df)
                result_df = result_df[result_df['time'] == context.previous_date]
        
                for stock in current_positions.keys():
                    stock_df_tmp = result_df[result_df['code'] == stock]
                    close = stock_df_tmp['close'].values[0]
                    bug_status = stock_df_tmp['卖'].values[0]
                    if bug_status == '卖':
                        log.debug("收益止盈,卖出{}".format(stock))
                        g.other_sale.append(stock)

# 动态调仓代码
def adjust_stock_num(context):
    ma_para = 10
    today = context.previous_date
    index_df = get_price('399101.XSHE', end_date=today, count=ma_para, fields='close', frequency='daily')
    ma = index_df['close'].mean()
    last_row = index_df['close'].iloc[-1]
    diff = last_row - ma
    
    result = 5 if diff >= 500 else \
             5 if 200 <= diff < 500 else \
             6 if -200 <= diff < 200 else \
             8 if -500 <= diff < -200 else \
             10
             
    stock_df = get_price(security=get_index_stocks('399101.XSHE')
                         , end_date=context.previous_date, frequency='daily'
                         , fields=['close', 'open'], count=1, panel=False)
    down_ratio = (1 - stock_df['close'] / stock_df['open']).mean()
    if down_ratio >= g.stoploss_market:
        log.debug("大盘惨跌,平均降幅{:.2%}".format(down_ratio))
        result = 0

    return result

# 过滤各种股票
def filter_stocks(context, stock_list):
    current_data = get_current_data()
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    
    filtered_stocks = []
    for stock in stock_list:
        if current_data[stock].paused:
            continue
        if current_data[stock].is_st:
            continue
        if '退' in current_data[stock].name:
            continue
        if stock.startswith('30') or stock.startswith('68') or stock.startswith('8') or stock.startswith('4'):
            continue
        if not (stock in context.portfolio.positions or last_prices[stock][-1] < current_data[stock].high_limit):
            continue
        if not (stock in context.portfolio.positions or last_prices[stock][-1] > current_data[stock].low_limit):
            continue
        start_date = get_security_info(stock).start_date
        if context.previous_date - start_date < timedelta(days=375):
            continue
        filtered_stocks.append(stock)
    return filtered_stocks

# 筛选审计意见
def filter_audit(context, code):
    lstd = context.previous_date
    last_year = lstd.replace(year=lstd.year - 3, month=1, day=1)
    q = query(finance.STK_AUDIT_OPINION.code, finance.STK_AUDIT_OPINION.report_type
              ).filter(finance.STK_AUDIT_OPINION.code == code, finance.STK_AUDIT_OPINION.pub_date >= last_year)
    df = finance.run_query(q)
    df['report_type'] = df['report_type'].astype(str)
    contains_nums = df['report_type'].str.contains(r'2|3|4|5')
    return not contains_nums.any()

# 买入模块
def buy_security(context, target_list, num):
    position_count = len(context.portfolio.positions)
    target_num = num
    if target_num != 0:
        value = context.portfolio.cash / target_num
        for stock in target_list:
            order_target_value(stock, value)
            log.info("买入[%s]（%s元）" % (stock, value))
            if len(context.portfolio.positions) == g.stock_num:
                break

# 判断今天是否跳过月份
def today_is_between(context):
    month = context.current_dt.month
    day = context.current_dt.day
    if month in g.pass_months:
        code = '399303.XSHE'
        close = history(count=3, unit='1d', field='close', security_list=[code], df=False, skip_paused=False, fq='none')[code]
        if close[-1] > close[-2] * 0.995 and close[-1] > close[-3] * 0.994:
            return True
        return False
    else:
        if (month == 12 or month == 3) and day >= 16:
            return False
        return True

# 平仓函数
def close_account(context):
    if not g.trading_signal:
        curr_data = get_current_data()
        # 卖出所有股票（除了货币基金）
        if len(g.hold_list) != 0 and g.hold_list != [g.money_etf]:
            for stock in g.hold_list:
                if stock == g.money_etf:
                    continue
                if curr_data[stock].last_price == curr_data[stock].low_limit or curr_data[stock].paused:
                    continue
                order_target_value(stock, 0)
                log.info("卖出[%s]" % (stock))
        
        # 空仓月期间，将全部资金买入货币基金
        cash = context.portfolio.cash
        if cash > 0:
            order_target_value(g.money_etf, cash)
            log.info('空仓月期间，买入货币基金ETF: {} 金额: {:.2f}'.format(g.money_etf, cash))

# 技术指标函数 (保留必要部分)
def RD(N, D=3):
    return np.round(N, D)

def RET(S, N=1):
    return np.array(S)[-N]

def ABS(S):
    return np.abs(S)

def MAX(S1, S2):
    return np.maximum(S1, S2)

def MIN(S1, S2):
    return np.minimum(S1, S2)

def IF(S, A, B):
    return np.where(S, A, B)

def AND(S1, S2):
    return np.logical_and(S1, S2)

def REF(S, N=1):
    return pd.Series(S).shift(N).values

def STD(S, N):
    return pd.Series(S).rolling(N).std(ddof=0).values

def SUM(S, N):
    return pd.Series(S).rolling(N).sum().values if N > 0 else pd.Series(S).cumsum().values

def HHV(S, N):
    return pd.Series(S).rolling(N).max().values

def LLV(S, N):
    return pd.Series(S).rolling(N).min().values

def EMA(S, N):
    return pd.Series(S).ewm(span=N, adjust=False).mean().values

def SMA(S, N, M=1):
    return pd.Series(S).ewm(alpha=M/N, adjust=False).mean().values