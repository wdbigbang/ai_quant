# 克隆自聚宽文章：https://www.joinquant.com/post/39252
# 标题：多因子选股研究之二：每月调仓10年6倍收益的多因子策略
# 作者：明时正位的桔子

# 导入函数库
import pandas as pd
import numpy as np
import datetime as dt
import matplotlib.pyplot as plt
from jqdata import *
from jqfactor import *
from dateutil.relativedelta import *

# 初始化函数，设定基准等等
def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)

    ### 股票相关设定 ###
    # 股票类每笔交易时的手续费是：买入时佣金万分之三，卖出时佣金万分之三加千分之一印花税, 每笔交易佣金最低扣5块钱
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003, close_commission=0.0003, min_commission=5), type='stock')
    
    # 仓位分成20份，部分优秀的股票可以占两份仓位
    g.N = 20
    to_buy = stock_pool(context)
    if len(to_buy) > 0:
        cash_per_stock = context.portfolio.available_cash / len(to_buy)
        for stock in to_buy:
            order_value(stock, cash_per_stock)
    
    run_monthly(handle_monthly,1)
    
def handle_monthly(context):
    if context.previous_date.month in [4,8]:    
    #if context.previous_date.month == 5 or context.previous_date.month == 9:
    #if True:
        print('调仓' + context.current_dt.strftime("%Y-%m-%d"))
    
        to_hold = stock_pool(context)
        if len(context.portfolio.positions) > 0:
            for stock in context.portfolio.positions:
                if stock not in to_hold:
                    order_target(stock,0)
        
        to_buy = [stock for stock in to_hold if stock not in context.portfolio.positions]
        if len(to_buy) > 0:
            cash_per_stock = context.portfolio.available_cash / len(to_buy)
            for stock in to_buy:
                order_value(stock, cash_per_stock)
    else:
        print('本月未调仓')
        
def stock_pool(context):
    
    stock_list = list(get_all_securities(types=['stock'], date=None).index)
    s_previous_date = context.previous_date.strftime("%Y-%m-%d")
    one_month_before = context.current_dt + relativedelta(months= -1)
    s_omb = one_month_before.strftime("%Y-%m-%d")
    # 过滤去年亏损的股票以及估值过高超过200倍PE的股票
    q = query(
        valuation.code,
        valuation.day,
        valuation.pe_ratio,
        valuation.pb_ratio,
        valuation.market_cap
    ).filter(
        valuation.code.in_(stock_list),
        valuation.pe_ratio > 5,
        valuation.pe_ratio < 200
        
    ).order_by(valuation.market_cap.desc())
    
    df_valuation = get_fundamentals(q, date = s_previous_date).set_index('code')
    # 过滤掉市值最大的前5%和最小的后10%的股票，这样可过滤掉退市股票以及市值过小的股票
    df_valuation = df_valuation.iloc[int(len(df_valuation)/20):int(len(df_valuation)-len(df_valuation)/20), :]
    stock_list = list(df_valuation.index)
    
    # 选出上市时间超过一年的股票
    q = query(
        finance.STK_LIST.code,
        finance.STK_LIST.start_date,
        finance.STK_LIST.state
        
    ).filter(finance.STK_LIST.code.in_(stock_list), 
             finance.STK_LIST.start_date < s_omb, 
             finance.STK_LIST.state == '正常上市'
    ).order_by(finance.STK_LIST.start_date.asc())
    
    df_LIST = finance.run_query(q).set_index('code')
    stock_list = list(df_LIST.index)
    
    
    # 获取财务数据
    q = query(
        indicator.code,
        indicator.pubDate,
        indicator.statDate,
        indicator.eps,
        indicator.roe,
        indicator.roa,
        indicator.net_profit_margin,
        indicator.gross_profit_margin,
        indicator.ocf_to_revenue,
        indicator.inc_operation_profit_year_on_year
    ).filter(
        indicator.code.in_(stock_list),
        indicator.ocf_to_revenue > 0
    )
    
    df_finance = get_fundamentals(q).set_index('code')
    
    # 去极值，去掉前后3%
    df_finance.sort_values(by='roe', ascending=False,inplace=True)
    df_finance = df_finance.iloc[int(len(df_finance)/30):int(len(df_finance)-len(df_finance)/30), :]
    df_finance.sort_values(by='gross_profit_margin', ascending=False,inplace=True)
    df_finance = df_finance.iloc[int(len(df_finance)/30):int(len(df_finance)-len(df_finance)/30), :]

    stock_list = list(df_finance.index)
    
    
    # 根据新的证券列表取聚宽因子
    jqf = ['book_to_price_ratio',
        'sales_to_price_ratio',
        'roe_ttm', 
        'total_asset_turnover_rate',
        'growth',
        'Price3M',       
        'market_cap']
    data = get_factor_values(stock_list,factors=jqf,start_date=s_previous_date, end_date=s_previous_date)
    
    # 替换列名
    i=0
    df=data[jqf[i]].T
    df.rename(columns={df.columns[0]:jqf[i]}, inplace=True)
    df_valuation = df.iloc[:,0:1].copy()
    df_valuation.sort_index(ascending=True,inplace=True)
    for i in range(1,len(jqf)):
        df=data[jqf[i]].T
        df.rename(columns={df.columns[0]:jqf[i]}, inplace=True)
        df.sort_index(ascending=True,inplace=True)
        df_valuation[jqf[i]] = df.iloc[:,0:1].copy()


    
    df_valuation.sort_index(ascending=True,inplace=True)
    df_score = df_valuation.iloc[:,0:1].copy()
    
    
    df_valuation['market_cap_log'] = np.log(df_valuation['market_cap'])
    
    # 计算得分
    df_score['market_cap_score'] = 100 * (df_valuation['market_cap_log']-df_valuation['market_cap_log'].min())/(df_valuation['market_cap_log'].max()-df_valuation['market_cap_log'].min())
    df_score['valuation_score'] = 100 * (df_valuation['book_to_price_ratio']-df_valuation['book_to_price_ratio'].min())/(df_valuation['book_to_price_ratio'].max()-df_valuation['book_to_price_ratio'].min())
    df_score['return_score'] = 100 * ((df_finance['roe']-df_finance['roe'].min())/(df_finance['roe'].max()-df_finance['roe'].min()))
    df_score['growth'] = 100 * ((df_finance['inc_operation_profit_year_on_year']-df_finance['inc_operation_profit_year_on_year'].min())/(df_finance['inc_operation_profit_year_on_year'].max()-df_finance['inc_operation_profit_year_on_year'].min()))
    
    # 取聚宽因子
    jqf = ['ROC20','CR20']
    data = get_factor_values(stock_list,factors=jqf,start_date=s_previous_date, end_date=s_previous_date)
    
    i = 0
    df = data[jqf[i]].T
    df.rename(columns={df.columns[0]:jqf[i]}, inplace=True)
    df_jqf = df.iloc[:,0:1].copy()
    df_jqf.sort_index(ascending=True,inplace=True)
    
    df_score['momentum'] = 100 * ((df_jqf[jqf[i]]-df_jqf[jqf[i]].min())/(df_jqf[jqf[i]].max()-df_jqf[jqf[i]].min()))
    
    
    # 计算总分
    df_score['total_score'] = df_score['return_score'] \
                            + df_score['growth'] \
                            + df_score['valuation_score'] \
                            - df_score['market_cap_score'] \
                            - df_score['momentum']
    # 排序
    df_score.sort_values(by='total_score', ascending=False, inplace=True)
    
    # 返回股票列表
    stock_list=list(df_score.iloc[:g.N,:].index)

    return stock_list
