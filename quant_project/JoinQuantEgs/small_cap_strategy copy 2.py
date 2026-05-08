# 小市值波段策略 v1.0
# ==============================
#
# 定版日期：2026-03-16
#
# ==================== 核心思路 ====================
#
# 【策略理念】
# 基于小市值溢价效应：小市值股票因流动性差、机构覆盖少、信息不对称，长期存在超额收益
# 通过波段交易+风控系统，在获取小市值溢价的同时控制回撤
#
# 【选股逻辑】
# 1. 指数池：深证100成分股（中小盘股为主）
# 2. ROE筛选：ROE > 0，剔除亏损企业
# 3. ROE改善筛选：取ROE改善最大的前30%（最新季度权重最高）
# 4. 市值排序：按流通市值从小到大排序，选最小市值股票
#
# 【交易逻辑】
# - 买入时间：09:31 开盘后买入
# - 卖出时间：14:49 尾盘卖出
# - 持仓数量：7只，平均分配资金
# - 每日调仓：根据最新选股结果调整持仓
#
# 【风控系统】
# 1. 止盈：涨幅 ≥ 8% 清仓（防止利润回吐）
# 2. 冷静期：3日连续跌幅 ≥ 2% 触发，持续5天空仓
# 3. 空仓月：4月空仓（历史统计高风险月份）
# 4. 空仓时持有货币基金：银华日利(511880.XSHG)
#
# 【策略特点】
# - 不做回补：卖出后不主动买回，简化策略逻辑
# - 冷静期机制：连续下跌后空仓观望，避免连续亏损
# - 月度风控：4月空仓，规避历史高风险月份
#
# 【参数说明】
# - g.buy_stock_count = 7      # 持仓数量
# - g.uprate = 8.0             # 止盈阈值 8%
# - g.downrate = None          # 关闭回补
# - g.roe_improve_top = 0.3    # ROE改善筛选比例
# - g.empty_months = [4]       # 空仓月份
#
# 【来源】
# - 基础框架：min_cooldown_swing_strategy（聚宽文章）
# - 优化思路：ai_debug.py SwingStrategy
# - ROE筛选：ROE+PB模型优化策略
#
# ================================================

from jqdata import *
from jqfactor import *
from jqlib.technical_analysis import *
import datetime as dt
import pandas as pd
import numpy as np
from datetime import datetime
from datetime import timedelta


def initialize(context):
    log.info("=" * 70)
    log.info("=== 小市值策略 v1.0 初始化 ===")
    log.info("=" * 70)

    set_option('use_real_price', True)

    set_option('avoid_future_data', True)

    set_benchmark('000300.XSHG')
        # 设置日志级别
    log.set_level('order', 'error')   # 订单日志只报错
    log.set_level('system', 'error')  # 系统日志只报错
    log.set_level('strategy', 'info') # 策略日志显示info信息
    set_benchmark('000300.XSHG')
    # 滑点与手续费（按聚宽写法）
    set_slippage(FixedSlippage(0.002))
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
                             open_commission=0.0003, close_commission=0.0003,
                             close_today_commission=0, min_commission=5), type='stock')

    # 指数池（中小板综），聚宽代码使用 XSHE
    g.index = '399101.XSHE'
    g.buy_stock_count = 7             # 方案B：持仓7只（原5只）
    g.screen_stock_count = 15
    g.down_stock_count = 15

    # ==================== ROE筛选参数 ====================
    g.roe_filter = True           # 是否启用ROE筛选
    g.roe_threshold = 0           # ROE阈值（简单筛选用）
    g.roe_improve_filter = True   # 是否启用ROE改善筛选
    g.roe_improve_top = 0.3       # ROE改善筛选取前30%

    # 运行状态
    g.stock_list = []           # 候选池
    g.position_last_map = []    # 持仓列表
    g.current_date = None
    g.handle_data_flag = False

    # 资金系数
    g.cache_cash = 1.0

    # 分钟风控与冷却期参数
    g.uprate = 8.0               # 止盈8%（回退原值）
    g.downrate = None            # 方案B：关闭回补（原-3%）
    g.sell_cooldown_days = 5     # 卖出后冷却天数（交易日）
    g.sold_stocks_dates = {}     # {code: 'YYYY-MM-DD'}
    g.today_bought_stocks = set()
    g.today_sold_stocks = set()
    g.in_cooldown = False
    g.last_sell_date = None
    g.last_cooldown_check_time = None
    g.days_since_sell = 0
    g.money_fund = '511880.XSHG'  # 冷静期持有的货币基金ETF
    g.buy_executed = False
    g.sell_executed = False
    g.empty_months=[4]

    # 冷静期（3日连续跌幅逻辑）参数与状态
    g.return_threshold = -0.02  # 单日跌幅阈值 -2%
    g.days=3
    g.cooldown_days=5
    g.cooldown_count = 0        # 冷静期次数
    g.cooldown_dates = []       # 冷静期起始日期记录
    g.portfolio_values = []     # 用于计算最近几日的组合市值

    # ==================== 打印参数 ====================
    log.info("[参数] 指数: %s" % g.index)
    log.info("[参数] 持仓数量: %d, 筛选数量: %d" % (g.buy_stock_count, g.screen_stock_count))
    log.info("[参数] ROE筛选: %s, 阈值: %s" % (g.roe_filter, g.roe_threshold))
    log.info("[参数] ROE改善筛选: %s, 比例: %.0f%%" % (g.roe_improve_filter, g.roe_improve_top * 100))
    log.info("[参数] 止盈阈值: %.1f%%" % g.uprate)
    log.info("[参数] 冷静期: %d天, 连续跌幅: %d天, 跌幅阈值: %.2f%%" % (g.cooldown_days, g.days, g.return_threshold * 100))
    log.info("[参数] 空仓月份: %s" % str(g.empty_months))
    log.info("[参数] 货币基金: %s" % g.money_fund)
    log.info("=" * 70)

    # 调度：盘前准备+固定时点交易
    run_daily(before_trading_start, time='09:25')
    run_daily(buy_stocks, time='09:31')
    run_daily(sell_stocks, time='14:49')

    # 冷静期检查定时任务
    run_daily(check_and_clean_stocks_in_cooldown, time='10:30')
    run_daily(check_and_clean_stocks_in_cooldown, time='13:30')
    run_daily(check_and_clean_stocks_in_cooldown, time='14:30')
    # 组合跌幅计算与3日连续跌幅触发
    run_daily(download_sell, time='09:30')

    # 在回测中用逐分钟调度近似分钟级风控
    for hour in range(9, 15):
        for minute in range(0, 60):
            current_time = "%02d:%02d" % (hour, minute)
            if ('09:31' < current_time < '11:30') or ('13:00' < current_time < '14:54'):
                run_daily(interval_sell_buy, time=current_time)


# 工具函数 ------------------------------------------------------------

def _get_prev_trade_day(context):
    # 取昨天交易日字符串
    ds = get_trade_days(end_date=context.current_dt.date(), count=2)
    if len(ds) >= 2:
        return str(ds[-2])
    return str(context.current_dt.date())


def _filter_st_pause_delist(codes):
    log.info("[过滤ST/停牌] 输入数量: %d" % len(codes))
    if not codes:
        return []
    current_data = get_current_data()
    out = []
    st_count = 0
    pause_count = 0
    name_count = 0
    for s in codes:
        try:
            info = current_data[s]
            name = info.name
            if info.is_st:
                st_count += 1
                continue
            if info.paused:
                pause_count += 1
                continue
            if name and ('退' in name or 'ST' in name or '*ST' in name):
                name_count += 1
                continue
            out.append(s)
        except:
            continue
    log.info("[过滤ST/停牌] ST=%d, 停牌=%d, 名称过滤=%d, 输出=%d" % (st_count, pause_count, name_count, len(out)))
    return out


def _get_universe(context):
    log.info("[获取股票池] 指数: %s" % g.index)
    try:
        pool = get_index_stocks(g.index)
        log.info("[获取股票池] 指数成分股数量: %d" % len(pool))
    except Exception as e:
        log.error("[获取股票池] 失败: %s" % str(e))
        pool = []
    return _filter_st_pause_delist(pool)


def _get_limit_rate(code, day_str, st_flag=False):
    # 涨跌幅限制（简化版）：主板10%，科创/新创 20%，ST 5%
    ymd = day_str.replace('-', '') if isinstance(day_str, str) else ''
    rate = 0.10
    if code.startswith('68'):
        rate = 0.20
    elif code.startswith('3') and ymd >= '20200824':  # 创业板注册制
        rate = 0.20
    elif st_flag:
        rate = 0.05
    return rate


def _get_today_high_limit_from_yclose(code, today_str, yclose):
    cd = get_current_data()
    st_flag = False
    try:
        st_flag = bool(cd[code].is_st)
    except:
        st_flag = False
    rate = _get_limit_rate(code, today_str, st_flag)
    return yclose * (1.0 + rate)


def _limit_flags_today(context, codes):
    # 返回 {'up_limit':[], 'down_limit':[]}（以昨收和当下价近似判定）
    if not codes:
        return {'up_limit': [], 'down_limit': []}
    today = str(context.current_dt.date())
    yday = _get_prev_trade_day(context)
    cd = get_current_data()
    up, down = [], []
    for s in codes:
        try:
            ybar = get_price(s, end_date=yday, count=1, frequency='daily', fields=['close'], skip_paused=False)
            if ybar is None or ybar.empty:
                continue
            yclose = float(ybar['close'].iloc[-1])
            # 当前价（分时）
            price = float(cd[s].last_price) if s in cd else yclose
            hl = _get_today_high_limit_from_yclose(s, today, yclose)
            ll = yclose * (1.0 - _get_limit_rate(s, today, cd[s].is_st if s in cd else False))
            if price >= hl - 1e-6:
                up.append(s)
            if price <= ll + 1e-6:
                down.append(s)
        except:
            continue
    return {'up_limit': list(set(up)), 'down_limit': list(set(down))}


# Helper: trading days since last sell

def _trading_days_since_last_sell(context):
    try:
        if not getattr(g, 'last_sell_date', None):
            return 0
        last = datetime.strptime(g.last_sell_date, '%Y-%m-%d').date()
        start = last + timedelta(days=1)
        days = get_trade_days(start_date=start, end_date=context.current_dt.date())
        return len(days)
    except Exception:
        return 0


# 核心流程 ------------------------------------------------------------

def before_trading_start(context):
    log.info("=" * 70)
    log.info("=== 盘前处理（聚宽版本）===")
    log.info("[聚宽对照] 日期: %s" % context.current_dt.strftime('%Y-%m-%d'))

    # 空仓月自动处理月初/月末货基
    if _is_empty_month(context):
        log.info("[空仓月] 当前是空仓月")
        if _is_first_trading_day_in_month(context):
            log.info("[空仓月] 月初第一个交易日")
            _enforce_empty_month_start(context)
        elif _is_last_trading_day_in_month(context):
            log.info("[空仓月] 月末最后一个交易日")
            _enforce_empty_month_end(context)

    # 生成候选股票池（指数成分 → ST/停牌/名称 过滤）
    g.stock_list = _get_universe(context)
    g.current_date = _get_prev_trade_day(context)
    log.info("[聚宽对照] 昨日日期: %s" % g.current_date)
    log.info("[聚宽对照] 股票池数量: %d" % len(g.stock_list))

    # 重置当日去重集与当日执行标记
    g.today_bought_stocks = set()
    g.today_sold_stocks = set()
    g.buy_executed = False
    g.sell_executed = False

    # 冷静期天数推进（按交易日计）
    g.days_since_sell = _trading_days_since_last_sell(context)
    log.info("[盘前] 冷静期天数: %d / %d, in_cooldown: %s" % (g.days_since_sell, g.cooldown_days, g.in_cooldown))

    # 冷静期内即时处理
    check_and_clean_stocks_in_cooldown(context)

    # ==================== 选股流程 ====================
    log.info("=" * 70)
    log.info("=== 选股流程开始（聚宽版本）===")
    log.info("[聚宽对照] 日期: %s" % g.current_date)

    # 步骤1：获取基本面数据
    log.info("-" * 50)
    log.info("[选股-步骤1] 获取市值数据")
    log.info("[聚宽对照] 输入数量: %d" % len(g.stock_list))
    try:
        q = query(valuation.code, valuation.circulating_market_cap, valuation.market_cap) \
            .filter(valuation.code.in_(g.stock_list))
        df = get_fundamentals(q, g.current_date)
        if df is None or df.empty:
            log.error("[选股-步骤1] 市值数据为空")
            g.handle_data_flag = False
            return
        log.info("[聚宽对照] 市值数据行数: %d" % len(df))
        log.info("[聚宽对照] 市值数据列名: %s" % str(df.columns.tolist()))

        # 打印市值数据样例（前5只）
        log.info("[聚宽对照] 市值数据样例（前5只）:")
        for i, row in df.head(5).iterrows():
            log.info("  %s: 流通市值=%.2f亿, 总市值=%.2f亿" % (row['code'], row['circulating_market_cap'], row['market_cap']))

        stock_pool = list(df['code'])
    except Exception as e:
        log.error('[选股-步骤1] 失败: %s' % e)
        g.handle_data_flag = False
        return

    # 步骤2：ROE筛选
    log.info("-" * 50)
    log.info("[选股-步骤2] ROE筛选")
    roe_before = len(stock_pool)
    log.info("[聚宽对照] ROE筛选前数量: %d" % roe_before)
    if g.roe_filter:
        stock_pool = _filter_by_roe(context, stock_pool)
        if not stock_pool:
            log.info('[选股] ROE筛选后为空')
            g.handle_data_flag = False
            return
    log.info("[聚宽对照] ROE筛选后数量: %d (过滤掉: %d)" % (len(stock_pool), roe_before - len(stock_pool)))

    # 步骤3：ROE改善筛选
    log.info("-" * 50)
    log.info("[选股-步骤3] ROE改善筛选")
    roe_after = len(stock_pool)
    log.info("[聚宽对照] ROE改善筛选前数量: %d" % roe_after)
    if g.roe_improve_filter:
        stock_pool = _filter_by_roe_improve(context, stock_pool)
        if not stock_pool:
            log.info('[选股] ROE改善后为空')
            g.handle_data_flag = False
            return
    log.info("[聚宽对照] ROE改善筛选后数量: %d (过滤掉: %d)" % (len(stock_pool), roe_after - len(stock_pool)))

    # 步骤4：按市值排序，保存结果
    log.info("-" * 50)
    log.info("[选股-步骤4] 按市值排序...")
    log.info("[聚宽对照] 最终选股输入数量: %d" % len(stock_pool))
    try:
        q = query(valuation.code, valuation.circulating_market_cap, valuation.market_cap) \
            .filter(valuation.code.in_(stock_pool))
        df = get_fundamentals(q, g.current_date)
        if df is None or df.empty:
            log.error("[选股-步骤4] 市值数据为空")
            g.handle_data_flag = False
            return
        df = df.sort_values(by='circulating_market_cap', ascending=True)
        g.df2 = df.set_index('code')

        log.info("[聚宽对照] 最终选股数量: %d" % len(g.df2))

        # 打印前10只股票（关键对照数据！）
        log.info("[聚宽对照] ========== 最终选股结果（前10只）==========")
        for i, (code, row) in enumerate(g.df2.head(10).iterrows(), 1):
            log.info("  %d. %s: 流通市值=%.2f亿" % (i, code, row['circulating_market_cap']))
        log.info("[聚宽对照] ============================================")

        g.handle_data_flag = True
        log.info('[选股] 完成: 候选 %d 只 -> 最终 %d 只' % (len(g.stock_list), len(g.df2)))
    except Exception as e:
        log.error('[选股-步骤4] 失败: %s' % e)
        g.handle_data_flag = False

    log.info("=" * 70)


def _filter_by_roe(context, stock_list):
    """ROE简单筛选：ROE > 阈值
    
    【新增调试】详细输出ROE计算相关信息，对比净利润数据
    """
    log.info("-" * 50)
    log.info("[ROE筛选] 开始（聚宽版本）")
    log.info("[聚宽对照] 输入数量: %d" % len(stock_list))
    log.info("[聚宽对照] ROE阈值: %s (ROE > 0)" % g.roe_threshold)
    
    if not stock_list:
        return []
    
    try:
        # ==================== 1. 获取indicator.roe ====================
        q = query(indicator.code, indicator.roe) \
            .filter(indicator.code.in_(stock_list))
        df = get_fundamentals(q, g.current_date)
        
        if df is None or df.empty:
            log.warning("[聚宽对照] ROE数据为空，返回原列表")
            return stock_list
        
        log.info("[聚宽对照] ROE数据行数: %d" % len(df))
        
        # ==================== 2. 详细调试 ====================
        debug_stocks = list(df['code'].head(5))
        log.info("[聚宽调试] === ROE定义验证（前5只股票）===")
        
        for stock in debug_stocks:
            roe_value = df[df['code'] == stock]['roe'].values[0]
            log.info("[聚宽调试] %s: indicator.roe=%.2f%%" % (stock, roe_value))
            
            # 获取净利润
            q_np = query(income.code, income.statDate, income.net_profit) \
                .filter(income.code == stock)
            df_np = get_fundamentals(q_np, g.current_date)
            
            if df_np is not None and not df_np.empty:
                df_np = df_np.sort_values('statDate', ascending=False)
                latest_np = df_np.iloc[0]['net_profit']
                latest_date = df_np.iloc[0]['statDate']
                log.info("  最新财报日期: %s, 净利润=%.2f亿" % (latest_date, latest_np/1e8))
            
            # 获取净资产（查询同一日期）
            q_eq = query(balance.code, balance.statDate, balance.total_owner_equities) \
                .filter(balance.code == stock)
            df_eq = get_fundamentals(q_eq, g.current_date)
            
            if df_eq is not None and not df_eq.empty:
                df_eq = df_eq.sort_values('statDate', ascending=False)
                latest_eq = df_eq.iloc[0]['total_owner_equities']
                eq_date = df_eq.iloc[0]['statDate']
                log.info("  净资产财报日期: %s, 净资产=%.2f亿" % (eq_date, latest_eq/1e8))
                
                # 计算ROE
                if df_np is not None and not df_np.empty:
                    calc_roe = (latest_np / latest_eq) * 100
                    log.info("  手动计算ROE = %.2f亿 / %.2f亿 = %.2f%%" % 
                             (latest_np/1e8, latest_eq/1e8, calc_roe))
                    log.info("  indicator.roe / 手动ROE = %.2f倍" % (roe_value / calc_roe if calc_roe > 0 else 0))
        
        log.info("[聚宽调试] ================================")
        
        # ==================== 3. ROE > 阈值筛选 ====================
        df = df[df['roe'] > g.roe_threshold]
        result = list(df['code'])
        
        log.info("[聚宽对照] ROE筛选后数量: %d (过滤掉: %d)" % (len(result), len(stock_list) - len(result)))
        log.info("[聚宽对照] ROE筛选后前5只: %s" % str(result[:5]))
        log.info("-" * 50)
        return result
    except Exception as e:
        log.error('[聚宽对照] ROE筛选失败: %s' % str(e))
        import traceback
        log.error(traceback.format_exc())
        return stock_list


def _filter_by_roe_improve(context, stock_list):
    """ROE改善筛选：取ROE改善最大的前X%"""
    log.info("-" * 50)
    log.info("[ROE改善筛选] 开始（聚宽版本）")
    log.info("[聚宽对照] 输入数量: %d" % len(stock_list))
    log.info("[聚宽对照] 改善比例: %.0f%% (取前30%%)" % (g.roe_improve_top * 100))

    if not stock_list:
        return []

    try:
        yesterday = g.current_date
        log.info("[聚宽对照] 查询日期: %s" % yesterday)

        interval = 1000
        stock_len = len(stock_list)

        if stock_len <= interval:
            df = get_history_fundamentals(stock_list, fields=[indicator.code, indicator.roe],
                                          watch_date=yesterday, count=5, interval='1q')
        else:
            df_num = stock_len // interval
            df = get_history_fundamentals(stock_list[:interval], fields=[indicator.code, indicator.roe],
                                          watch_date=yesterday, count=5, interval='1q')
            for i in range(df_num):
                dfi = get_history_fundamentals(
                    stock_list[interval*(i+1):min(stock_len, interval*(i+2))],
                    fields=[indicator.code, indicator.roe],
                    watch_date=yesterday, count=5, interval='1q')
                df = df.append(dfi)

        if df is None or df.empty:
            log.warning("[聚宽对照] ROE改善数据为空，返回原列表")
            return stock_list

        log.info("[聚宽对照] 获取到数据行数: %d" % len(df))
        log.info("[聚宽对照] 数据列名: %s" % str(df.columns.tolist()))

        # 打印原始数据样例（前5行）
        log.info("[聚宽对照] 原始数据样例（前5行）:")
        for i, row in df.head(5).iterrows():
            log.info("  %s: ROE=%.4f" % (row['code'], row['roe']))

        # 关键步骤：unstack
        df = df.groupby('code').apply(lambda x: x.reset_index()).roe.unstack()
        log.info("[聚宽对照] unstack后行数: %d, 列数: %d" % (len(df), len(df.columns)))
        log.info("[聚宽对照] unstack后列名: %s" % str(df.columns.tolist()))

        # 打印unstack后数据样例
        log.info("[聚宽对照] unstack后数据样例（前5只）:")
        for code in list(df.index)[:5]:
            log.info("  %s: ROE_1=%.2f, ROE_2=%.2f, ROE_3=%.2f, ROE_4=%.2f, ROE_5=%.2f" %
                     (code, df.loc[code].iloc[0], df.loc[code].iloc[1], df.loc[code].iloc[2],
                      df.loc[code].iloc[3], df.loc[code].iloc[4]))

        # 计算改善值
        df['increase'] = 4*df.iloc[:,4] - df.iloc[:,0] - df.iloc[:,1] - df.iloc[:,2] - df.iloc[:,3]
        df.dropna(inplace=True)
        df.sort_values(by='increase', ascending=False, inplace=True)

        log.info("[聚宽对照] 计算改善后行数: %d" % len(df))

        # 打印改善值最大的前5只
        log.info("[聚宽对照] 改善值最大的前5只:")
        for code in list(df.index)[:5]:
            log.info("  %s: 改善值=%.4f" % (code, df.loc[code, 'increase']))

        top_count = max(1, int(len(df) * g.roe_improve_top))
        result = list(df.index)[:top_count]

        log.info("[聚宽对照] ROE改善筛选后数量: %d (过滤掉: %d)" % (len(result), len(stock_list) - len(result)))
        log.info("[聚宽对照] ROE改善筛选后前5只: %s" % str(result[:5]))
        log.info("-" * 50)
        return result
    except Exception as e:
        log.error('[聚宽对照] ROE改善筛选失败: %s' % str(e))
        return stock_list


def _get_trade_stocks(context, mode='sell'):
    log.info("[获取交易股票] 模式: %s" % mode)
    
    # 基于昨日财务+当下价格，计算当前流通市值近似，并筛选
    if not getattr(g, 'df2', None) is not None or g.df2.empty:
        log.warning("[获取交易股票] g.df2 为空")
        return []
    df = g.df2.copy()
    log.info("[获取交易股票] g.df2 行数: %d" % len(df))
    
    cd = get_current_data()

    # 用当前价近似"当前流通市值"
    df['curr_float_value'] = np.nan
    for code in df.index.tolist():
        try:
            px = cd[code].last_price
            if not np.isnan(px) and px > 0:
                # circulating_market_cap 单位：亿元；乘以（当下价/昨收）近似
                ybar = get_price(code, end_date=g.current_date, count=1, frequency='daily', fields=['close'])
                yclose = float(ybar['close'].iloc[-1]) if ybar is not None and not ybar.empty else px
                scale = px / yclose if yclose > 0 else 1.0
                df.loc[code, 'curr_float_value'] = df.loc[code, 'circulating_market_cap'] * scale
        except:
            df.loc[code, 'curr_float_value'] = np.nan

    df = df.dropna(subset=['curr_float_value'])
    log.info("[获取交易股票] 有效市值数据行数: %d" % len(df))
    
    if df.empty:
        return []

    # 按"当前流通市值"升序 + 代码排序，取前 screen_stock_count
    df['code2'] = df.index
    df = df.sort_values(by=['curr_float_value', 'code2'], ascending=[True, True])
    
    log.info("[获取交易股票] 当前流通市值前5:")
    for code, row in df.head(5).iterrows():
        log.info("  %s: 流通市值=%.2f亿" % (code, row['curr_float_value']))
    
    stocks = df.head(g.screen_stock_count).index.tolist()

    # 涨停过滤：剔除当前涨停的标的
    lim = _limit_flags_today(context, stocks)
    up_limit_stock = set(lim['up_limit'])
    log.info("[获取交易股票] 涨停股票数量: %d" % len(up_limit_stock))
    stocks = [s for s in stocks if s not in up_limit_stock]

    # 已持仓中涨停的保留（不参与换仓）
    hold_codes = list(context.portfolio.positions.keys())
    lim_hold = _limit_flags_today(context, hold_codes)
    hold_up = set(lim_hold['up_limit'])
    log.info("[获取交易股票] 持仓中涨停数量: %d" % len(hold_up))

    # 返回数量控制
    if mode == 'sell':
        need_num= max(0, g.down_stock_count - len(hold_up))
    else:
        need_num = max(0, g.buy_stock_count - len(hold_up))

    final_list = list(hold_up) + stocks[:need_num]
    log.info("[获取交易股票] 最终数量: %d (涨停保留: %d, 新选: %d)" % (len(final_list), len(hold_up), min(need_num, len(stocks))))
    return final_list


def sell_stocks(context):
    log.info("=" * 70)
    log.info("=== 卖出 (14:49) ===")
    
    if not g.handle_data_flag:
        log.info("[卖出] handle_data_flag=False，跳过")
        return

    # 生成应持仓列表（卖出：不在列表内的尽量卖出）
    target_list = _get_trade_stocks(context, mode='sell')
    target_set = set(target_list)
    log.info("[卖出] 目标持仓: %s" % str(target_list[:10]))

    for code, pos in list(context.portfolio.positions.items()):
        try:
            # 冷静期期间：不卖出货币基金
            if code == g.money_fund and getattr(g, 'in_cooldown', False):
                continue
            # 空仓月期间：货基仅在月末卖出，其余时间不卖
            if code == g.money_fund and _is_empty_month(context):
                if _is_last_trading_day_in_month(context):
                    if pos.total_amount > 0:
                        order_target_value(code, 0)
                        log.info('空仓月月末，卖出货币基金ETF: {}'.format(code))
                continue

            cd = get_current_data()[code]
            # 强制卖出 ST/退市/停牌恢复后：仅在可卖出时
            if cd.is_st or ('退' in cd.name if cd.name else False):
                order_target(code, 0)
                log.info('强制卖出ST/退: {}'.format(code))
                continue
            if code not in target_set:
                order_target(code, 0)
                log.info('卖出: {}, 数量: {}'.format(code, pos.total_amount))
        except Exception as e:
            log.warn('卖出处理异常 {}: {}'.format(code, e))
    
    log.info("=" * 70)


def buy_stocks(context):
    log.info("=" * 70)
    log.info("=== 买入 (09:31) ===")
    
    if not g.handle_data_flag:
        log.info("[买入] handle_data_flag=False，跳过")
        return

    # 空仓月内不买入
    if _is_empty_month(context):
        log.info("[买入] 空仓月，不买入")
        return

    # 冷静期内不买入（按交易日计）
    if g.in_cooldown and g.days_since_sell < g.cooldown_days:
        log.info("[买入] 冷静期内，不买入 (%d/%d)" % (g.days_since_sell, g.cooldown_days))
        return

    # 生成应买入列表（买入：不在持仓内的尽量补齐到 g.buy_stock_count）
    targets = _get_trade_stocks(context, mode='buy')
    if not targets:
        log.info("[买入] 目标列表为空")
        return

    # 已持仓（仅统计可用持仓）
    held = [c for c, p in context.portfolio.positions.items() if p.total_amount > 0]
    need_num = max(0, g.buy_stock_count - len(held))
    
    log.info("[买入] 已持仓: %d, 目标: %d, 需买入: %d" % (len(held), g.buy_stock_count, need_num))
    
    if need_num <= 0:
        log.info("[买入] 已满仓，无需买入")
        return

    cash = context.portfolio.cash * g.cache_cash
    per_value = cash / float(need_num) if need_num > 0 else 0
    
    log.info("[买入] 可用资金: %.2f, 每只金额: %.2f" % (cash, per_value))

    for code in targets:
        if code in held:
            continue
        if per_value <= 0:
            break
        try:
            order_target_value(code, per_value)
            log.info('买入: {} 目标金额: {:.2f}'.format(code, per_value))
            held.append(code)
            need_num -= 1
            if need_num <= 0:
                break
        except Exception as e:
            log.warn('买入失败 {}: {}'.format(code, e))
    
    log.info("=" * 70)


# 可选：回测结束后打印简单总结
def after_trading_end(context):
    log.info("=" * 70)
    log.info("=== 盘后处理 ===")
    log.info("日期: %s" % context.current_dt.strftime('%Y-%m-%d'))

    positions = context.portfolio.positions
    log.info("[盘后] 持仓数量: %d" % len(positions))
    for code, pos in positions.items():
        if pos.total_amount > 0:
            log.info("  %s: 数量=%d" % (code, pos.total_amount))

    log.info("[盘后] 总资产: %.2f, 现金: %.2f" % (context.portfolio.total_value, context.portfolio.cash))
    log.info("=" * 70)


def _can_buy_after_cooldown(context, code):
    if code not in g.sold_stocks_dates:
        return True
    try:
        last = datetime.strptime(g.sold_stocks_dates[code], '%Y-%m-%d').date()
        # 计算交易日间隔
        start = last + timedelta(days=1)
        days = get_trade_days(start_date=start, end_date=context.current_dt.date())
        return len(days) >= getattr(g, 'cooldown_days', 5)
    except:
        return True


def interval_sell_buy(context):
    # 空仓月或冷静期内不执行分钟风控
    if _is_empty_month(context) or getattr(g, 'in_cooldown', False):
        return

    # 分钟级风控：涨幅达到 uprate% 则清仓；跌幅达到 downrate% 且当日未买过且不在冷却期可买回
    cd = get_current_data()
    today_str = str(context.current_dt.date())

    # 卖出逻辑（止盈）
    for code, pos in list(context.portfolio.positions.items()):
        try:
            if pos.total_amount <= 0:
                continue
            # 涨跌幅基准：昨收
            yday = _get_prev_trade_day(context)
            ybar = get_price(code, end_date=yday, count=1, frequency='daily', fields=['close'])
            if ybar is None or ybar.empty:
                continue
            yclose = float(ybar['close'].iloc[-1])
            last = float(cd[code].last_price) if code in cd else yclose
            pct = (last / yclose - 1.0) * 100.0 if yclose > 0 else 0.0
            if pct >= g.uprate and code not in g.today_sold_stocks:
                order_target(code, 0)
                g.today_sold_stocks.add(code)
                g.sold_stocks_dates[code] = today_str
                g.last_sell_date = today_str
                log.info('分钟止盈 卖出: {} 涨幅: {:.2f}%'.format(code, pct))
        except Exception as e:
            log.warn('分钟止盈处理失败 {}: {}'.format(code, e))

    # 买回逻辑（可选：跌幅触发）
    if g.downrate is not None:
        cash = context.portfolio.cash
        for code in list(context.portfolio.positions.keys()):
            try:
                pos = context.portfolio.positions[code]
                if pos.total_amount > 0:
                    continue
            except:
                pass
            try:
                if code in g.today_bought_stocks:
                    continue
                if g.in_cooldown and g.days_since_sell < g.cooldown_days:
                    continue
                if not _can_buy_after_cooldown(context, code):
                    continue
                yday = _get_prev_trade_day(context)
                ybar = get_price(code, end_date=yday, count=1, frequency='daily', fields=['close'])
                if ybar is None or ybar.empty:
                    continue
                yclose = float(ybar['close'].iloc[-1])
                last = float(cd[code].last_price) if code in cd else yclose
                pct = (last / yclose - 1.0) * 100.0 if yclose > 0 else 0.0
                if pct <= g.downrate:
                    per_value = context.portfolio.total_value / float(max(1, g.buy_stock_count))
                    if per_value > 0 and cash > 0:
                        value = min(per_value, cash)
                        order_value(code, value)
                        g.today_bought_stocks.add(code)
                        log.info('分钟触发回补 买入: {} 跌幅: {:.2f}% 金额: {:.2f}'.format(code, pct, value))
                        cash -= value
                        if cash <= 0:
                            break
            except Exception as e:
                log.warn('分钟买入处理失败 {}: {}'.format(code, e))


def check_and_clean_stocks_in_cooldown(context):
    """冷静期管理：在冷静期内清空股票并持有货币基金；到期后退出冷静期。"""
    # 未开启或未处于冷静期则返回
    if not getattr(g, 'in_cooldown', False):
        return
    
    log.info("-" * 50)
    log.info("[冷静期检查]")

    # 推进冷静期天数（按交易日计）
    g.days_since_sell = _trading_days_since_last_sell(context)
    log.info("[冷静期检查] 天数: %d / %d" % (g.days_since_sell, g.cooldown_days))

    # 到期：卖出货币基金并退出冷静期
    if g.last_sell_date and g.days_since_sell >= g.cooldown_days:
        log.info("[冷静期] 到期，退出冷静期")
        try:
            if g.money_fund in context.portfolio.positions:
                pos = context.portfolio.positions[g.money_fund]
                amt = getattr(pos, 'total_amount', 0)
                if amt >= 100:
                    order_target_value(g.money_fund, 0)
                    log.info('冷静期结束，卖出货币基金ETF: {}'.format(g.money_fund))
                else:
                    log.info('冷静期结束，但货基持仓不足100股(amt={})，暂不卖出'.format(amt))
        except Exception as e:
            log.warn('退出冷静期时卖出货基失败: {}'.format(e))
        g.in_cooldown = False
        return

    # 冷静期内：清空所有股票（除货基）
    for code, pos in list(context.portfolio.positions.items()):
        if code == g.money_fund:
            continue
        try:
            if pos.total_amount > 0:
                order_target_value(code, 0)
                log.info('冷静期内卖出股票: {}'.format(code))
        except Exception as e:
            log.warn('冷静期内清仓失败 {}: {}'.format(code, e))

    # 用余额买入货币基金（仅加仓，不减仓；满足100股最小交易单位）
    try:
        cd = get_current_data()
        price = float(cd[g.money_fund].last_price) if g.money_fund in cd else None
        if price is None or price <= 0:
            # 兜底用昨收
            ybar = get_price(g.money_fund, end_date=_get_prev_trade_day(context), count=1, frequency='daily', fields=['close'])
            if ybar is not None and not ybar.empty:
                price = float(ybar['close'].iloc[-1])
        if price and price > 0:
            cash = context.portfolio.cash
            pos = context.portfolio.positions.get(g.money_fund, None)
            cur_amt = getattr(pos, 'total_amount', 0) if pos else 0
            cur_val = cur_amt * price
            # 仅当现金可买入至少100股时才加仓
            lot_cash = price * 100
            if cash >= lot_cash:
                target_val = cur_val + cash
                order_target_value(g.money_fund, target_val)
                log.info('冷静期持有货币基金ETF: {} 金额: {:.2f}'.format(g.money_fund, target_val))
            else:
                # 仅记录当前持有金额
                log.info('冷静期持有货币基金ETF: {} 金额: {:.2f}'.format(g.money_fund, cur_val))
        else:
            log.info('冷静期持有货基：价格获取失败，跳过加仓')
    except Exception as e:
        log.warn('冷静期买入货基失败: {}'.format(e))


def _enter_cooldown(context, reason=''):
    # 清空股票并持有货币基金，标记冷静期
    try:
        # 清空所有非货基
        for code, pos in list(context.portfolio.positions.items()):
            if code == g.money_fund:
                continue
            if pos.total_amount > 0:
                order_target_value(code, 0)
        # 买入货基
        cash = context.portfolio.cash
        if cash > 0:
            order_target_value(g.money_fund, cash)
        g.in_cooldown = True
        g.last_sell_date = context.current_dt.strftime('%Y-%m-%d')
        log.info('进入冷静期: {} 货基持有金额: {:.2f}'.format(reason, context.portfolio.cash))
    except Exception as e:
        log.warn('进入冷静期失败: {}'.format(e))


# 空仓月（不交易月份）支持 ------------------------------------------------------------

def _is_empty_month(context):
    try:
        mon = context.current_dt.month
        return hasattr(g, 'empty_months') and (mon in g.empty_months)
    except Exception:
        return False


def _is_first_trading_day_in_month(context):
    try:
        cur = context.current_dt.date()
        month_start = cur.replace(day=1)
        days = get_trade_days(start_date=month_start, end_date=cur)
        return len(days) == 1 and days[0] == cur
    except Exception:
        return False


def _is_last_trading_day_in_month(context):
    try:
        cur = context.current_dt.date()
        month_start = cur.replace(day=1)
        # 下月1号
        if cur.month == 12:
            next_month_start = cur.replace(year=cur.year+1, month=1, day=1)
        else:
            next_month_start = cur.replace(month=cur.month+1, day=1)
        days_all = get_trade_days(start_date=month_start, end_date=next_month_start - timedelta(days=1))
        return len(days_all) > 0 and days_all[-1] == cur
    except Exception:
        return False


def _enforce_empty_month_start(context):
    # 月初：清空股票并买入货币基金
    try:
        # 卖出所有非货基
        for code, pos in list(context.portfolio.positions.items()):
            if code == g.money_fund:
                continue
            if pos.total_amount > 0:
                order_target_value(code, 0)
        # 买入货基
        cash = context.portfolio.cash
        if cash > 0:
            order_target_value(g.money_fund, cash)
            log.info('空仓月开始，买入货币基金ETF: {} 金额: {:.2f}'.format(g.money_fund, cash))
    except Exception as e:
        log.warn('空仓月开始操作失败: {}'.format(e))


def _enforce_empty_month_end(context):
    # 月末：卖出货币基金
    try:
        if g.money_fund in context.portfolio.positions and context.portfolio.positions[g.money_fund].total_amount > 0:
            order_target_value(g.money_fund, 0)
            log.info('空仓月结束，卖出货币基金ETF: {}'.format(g.money_fund))
    except Exception as e:
        log.warn('空仓月结束操作失败: {}'.format(e))

# -- 组合跌幅与三日连续触发冷静期 --

def calculate_portfolio_return(context):
    current_total_value = context.portfolio.total_value
    g.portfolio_values.append(current_total_value)
    if len(g.portfolio_values) > 4:
        g.portfolio_values.pop(0)
    
    log.info("[组合收益] 当前市值: %.2f, 记录长度: %d" % (current_total_value, len(g.portfolio_values)))
    
    if len(g.portfolio_values) >= 2:
        yesterday_value = g.portfolio_values[-2]
        if yesterday_value > 0:
            daily_return = (current_total_value - yesterday_value) / yesterday_value
            log.info("[组合收益] 日收益率: %.2f%%" % (daily_return * 100))
            return daily_return
    return 0.0


def check_portfolio_decline(context):
    # 需要至少 g.days+1 个数据点来计算最近 g.days 天的跌幅
    need_num = int(getattr(g, 'days', 3))
    log.info("[组合跌幅] 检查, 需要 %d 个数据点, 当前 %d 个" % (need_num + 1, len(g.portfolio_values)))
    
    if len(g.portfolio_values) < need_num + 1:
        return False
    
    decline_days = 0
    for i in range(need_num):
        newer = g.portfolio_values[-(i+1)]
        older = g.portfolio_values[-(i+2)]
        if older > 0:
            daily_ret = (newer - older) / older
            log.info("[组合跌幅] 第%d天: %.2f%%, 阈值: %.2f%%, 触发: %s" % 
                     (i+1, daily_ret * 100, g.return_threshold * 100, daily_ret <= g.return_threshold))
            if daily_ret <= g.return_threshold:
                decline_days += 1
    
    log.info("[组合跌幅] 连续下跌天数: %d, 需要天数: %d" % (decline_days, need_num))
    
    if decline_days >= need_num:
        # 触发冷静期：清仓并买入货基
        for code, pos in list(context.portfolio.positions.items()):
            try:
                order_target_value(code, 0)
            except Exception:
                continue
        try:
            cash = context.portfolio.cash
            if cash > 0:
                order_target_value(g.money_fund, cash)
        except Exception:
            pass
        g.in_cooldown = True
        g.cooldown_count += 1
        d = context.current_dt.strftime('%Y-%m-%d')
        g.cooldown_dates.append(d)
        g.last_sell_date = d
        g.days_since_sell = 0
        g.portfolio_values = []  # 清空记录，避免重复触发
        log.info('[冷静期触发] 连续%d天跌幅，日期: %s, 累计次数: %d' % (need_num, d, g.cooldown_count))
        return True
    return False


def download_sell(context):
    log.info("-" * 50)
    log.info("[09:30] 组合跌幅检查")
    # 每日记录组合涨跌并检查是否进入冷静期
    _ = calculate_portfolio_return(context)
    if check_portfolio_decline(context):
        log.info('[09:30] 已进入冷静期')