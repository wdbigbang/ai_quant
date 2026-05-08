# 行业哨兵策略（Sector Sentinel Strategy）v1.0 - 聚宽版本（详细日志版）
# ==============================
#
# 【策略概述】
# 通过监测"四大搅屎棍"（银行、有色、煤炭、钢铁）的行业宽度信号判断市场状态
# - 搅屎棍领涨 → 市场避险情绪强 → 空仓（跑）
# - 搅屎棍不领涨 → 市场正常 → 开仓买小市值优质股
#
# 【核心逻辑】
# 1. 计算行业宽度：每个行业有多少股票高于20日均线
# 2. 判断搅屎棍是否领涨：银行、有色、煤炭、钢铁是否在行业宽度前列
# 3. 择时决策：搅屎棍领涨 → 空仓；不领涨 → 买入小市值优质股
#
# 【选股逻辑】（开仓时）
# - 股票池：深证100成分股（中小盘为主）
# - 财务筛选：ROE > 15%, ROA > 10%（高质量）
# - 市值排序：按市值从小到大，取最小市值（小市值溢价）
#
# 【调仓规则】
# - 每周一调仓（周一9:30）
# - 涨停处理：每日14:00检查，涨停打开则卖出
#
# 【参数说明】
# - g.stock_num = 10     # 持仓数量
# - g.num = 1            # 取涨幅最大的行业数量（1=只看第一名）
# - 四大搅屎棍：银行(801780)、有色金属(801050)、煤炭(801950)、钢铁(801040)
#
# 【来源】
# - 聚宽文章：https://www.joinquant.com/post/49085
# - 作者：MarioC
#
# 【PTrade移植要点】（待移植时参考）
# 1. run_daily/run_weekly → before_trading_start + handle_data 手动调度
# 2. get_industry/get_industry_stocks → PTrade需要查找替代API
# 3. 股票代码：.XSHG/.XSHE → .SS/.SZ
# 4. context.previous_date → PTrade可能用不同属性
#
# ==============================

from jqdata import *
from jqfactor import *
import numpy as np
import pandas as pd
import pickle
from six import StringIO, BytesIO
import talib
import datetime


# ============================================================
#                    行业代码映射表
# ============================================================

SW1 = {
    '801010': '农林牧渔I',
    '801020': '采掘I',
    '801030': '化工I',
    '801040': '钢铁I',          # 【搅屎棍】
    '801050': '有色金属I',      # 【搅屎棍】
    '801060': '建筑建材I',
    '801070': '机械设备I',
    '801080': '电子I',
    '801090': '交运设备I',
    '801100': '信息设备I',
    '801110': '家用电器I',
    '801120': '食品饮料I',
    '801130': '纺织服装I',
    '801140': '轻工制造I',
    '801150': '医药生物I',
    '801160': '公用事业I',
    '801170': '交通运输I',
    '801180': '房地产I',
    '801190': '金融服务I',
    '801200': '商业贸易I',
    '801210': '休闲服务I',
    '801220': '信息服务I',
    '801230': '综合I',
    '801710': '建筑材料I',
    '801720': '建筑装饰I',
    '801730': '电气设备I',
    '801740': '国防军工I',
    '801750': '计算机I',
    '801760': '传媒I',
    '801770': '通信I',
    '801780': '银行I',         # 【搅屎棍】
    '801790': '非银金融I',
    '801880': '汽车I',
    '801890': '机械设备I',
    '801950': '煤炭I',         # 【搅屎棍】
    '801960': '石油石化I',
    '801970': '环保I',
    '801980': '美容护理I'
}

# 用于计算行业宽度的行业代码列表（剔除部分行业）
INDUSTRY_CODES = [
    '801010', '801020', '801030', '801040', '801050', '801080', '801110', '801120', 
    '801130', '801140', '801150', '801160', '801170', '801180', '801200', '801210', 
    '801230', '801710', '801720', '801730', '801740', '801750', '801760', '801770', 
    '801780', '801790', '801880', '801890'
]

# 【关键】四大搅屎棍行业代码
BASTION_CODES = ['801780', '801050', '801950', '801040']  # 银行、有色金属、煤炭、钢铁
BASTION_NAMES = ['银行I', '有色金属I', '煤炭I', '钢铁I']


# ============================================================
#                    初始化函数
# ============================================================

def initialize(context):
    log.info("=" * 70)
    log.info("=== 行业哨兵策略 v1.0 初始化 ===")
    log.info("=" * 70)
    
    # ==================== 基本设置 ====================
    set_benchmark('000985.XSHG')  # 中证全指
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    
    # ==================== 滑点与手续费 ====================
    # 【修复】原滑点设为0不合理，改为0.002（0.2%）
    set_slippage(FixedSlippage(0.002))
    set_order_cost(OrderCost(
        open_tax=0, 
        close_tax=0.001,           # 卖出印花税0.1%
        open_commission=0.0003,    # 买入佣金0.03%
        close_commission=0.0003,   # 卖出佣金0.03%
        close_today_commission=0, 
        min_commission=5           # 最小佣金5元
    ), type='stock')
    
    # ==================== 日志级别 ====================
    log.set_level('order', 'error')
    log.set_level('system', 'error')
    
    # ==================== 策略参数 ====================
    g.stock_num = 10        # 持仓数量
    g.num = 1               # 取涨幅最大的行业数量（只看第一名）
    
    # ==================== 持仓状态 ====================
    g.hold_list = []            # 当前持仓股票列表
    g.yesterday_HL_list = []    # 昨日涨停股票列表
    g.current_date = None       # 当前日期
    g.handle_data_flag = False  # 是否允许交易
    
    # ==================== 择时信号 ====================
    g.market_state = "normal"   # 市场状态：normal/defense
    g.bastion_in_top = False    # 搅屎棍是否在行业宽度前列
    g.market_breadth = 0        # 全市场宽度
    
    # ==================== 打印参数 ====================
    log.info("[参数] 持仓数量: %d" % g.stock_num)
    log.info("[参数] 行业数量(g.num): %d (只看第一名)" % g.num)
    log.info("[参数] 四大搅屎棍: %s" % str(BASTION_NAMES))
    log.info("=" * 70)
    
    # ==================== 调度函数 ====================
    # 【注意】PTrade不支持run_daily/run_weekly，需要改用手动调度
    run_daily(prepare_stock_list, '9:05')
    run_weekly(weekly_adjustment, 1, '9:30')    # 每周一调仓
    run_daily(check_limit_up, '14:00')          # 每日检查涨停


# ============================================================
#                    盘前准备函数
# ============================================================

def prepare_stock_list(context):
    """盘前准备：更新持仓列表、涨停列表"""
    log.info("=" * 70)
    log.info("=== 盘前准备（09:05）===")
    log.info("[日期] %s" % context.current_dt.strftime('%Y-%m-%d'))
    
    # ==================== 更新持仓列表 ====================
    g.hold_list = []
    for position in list(context.portfolio.positions.values()):
        stock = position.security
        g.hold_list.append(stock)
    
    log.info("[持仓] 当前持仓数量: %d" % len(g.hold_list))
    if g.hold_list:
        log.info("[持仓] 持仓列表: %s" % str(g.hold_list))
    
    # ==================== 获取昨日涨停列表 ====================
    g.yesterday_HL_list = []
    if g.hold_list:
        try:
            df = get_price(g.hold_list, end_date=context.previous_date, 
                           frequency='daily', fields=['close', 'high_limit'],
                           count=1, panel=False, fill_paused=False)
            df = df[df['close'] == df['high_limit']]
            g.yesterday_HL_list = list(df.code)
            
            if g.yesterday_HL_list:
                log.info("[涨停] 昨日涨停股票: %s" % str(g.yesterday_HL_list))
            else:
                log.info("[涨停] 无昨日涨停股票")
        except Exception as e:
            log.error("[涨停] 获取失败: %s" % str(e))
    
    # ==================== 更新当前日期 ====================
    g.current_date = context.previous_date
    log.info("[日期] previous_date: %s" % g.current_date)
    
    log.info("=" * 70)


# ============================================================
#                    行业宽度计算（核心择时）
# ============================================================

def get_stock_list(context):
    """
    核心选股模块：通过行业宽度判断市场状态
    
    步骤：
    1. 计算各行业的宽度（多少股票高于20日均线）
    2. 判断搅屎棍是否在行业宽度前列
    3. 择时决策：搅屎棍领涨 → 空仓；不领涨 → 买入小市值
    """
    log.info("=" * 70)
    log.info("=== 选股模块（核心择时）===")
    
    # ==================== 时间参数 ====================
    yesterday = context.previous_date
    today = context.current_dt
    log.info("[时间] yesterday: %s, today: %s" % (yesterday, today.strftime('%Y-%m-%d')))
    
    final_list = []
    
    # ==================== 步骤1：获取基准指数成分股 ====================
    log.info("-" * 50)
    log.info("[步骤1] 获取基准指数成分股")
    try:
        initial_list = get_index_stocks('000985.XSHG', today)  # 中证全指
        log.info("[步骤1] 中证全指成分股数量: %d" % len(initial_list))
        log.info("[步骤1] 成分股样例（前5只）: %s" % str(initial_list[:5]))
    except Exception as e:
        log.error("[步骤1] 获取成分股失败: %s" % str(e))
        return []
    
    # ==================== 步骤2：计算行业宽度 ====================
    log.info("-" * 50)
    log.info("[步骤2] 计算行业宽度")
    
    p_count = 1
    p_industries_type = 'sw_l1'  # 申万一级行业
    
    try:
        # 获取价格数据（21天用于计算20日均线）
        h = get_price(initial_list, end_date=yesterday, frequency='1d', 
                       fields=['close'], count=p_count + 20, panel=False)
        
        log.info("[步骤2] 价格数据行数: %d" % len(h))
        log.info("[步骤2] 价格数据列: %s" % str(h.columns.tolist()))
        
        # 构建价格矩阵
        h['date'] = pd.DatetimeIndex(h.time).date
        df_close = h.pivot(index='code', columns='date', values='close').dropna(axis=0)
        
        log.info("[步骤2] 价格矩阵行数: %d（有效股票数）" % len(df_close))
        log.info("[步骤2] 价格矩阵列数: %d（交易日数）" % len(df_close.columns))
        
        # 计算20日均线
        df_ma20 = df_close.rolling(window=20, axis=1).mean().iloc[:, -p_count:]
        
        # 计算宽度：价格是否高于20日均线
        df_bias = (df_close.iloc[:, -p_count:] > df_ma20)
        
        log.info("[步骤2] 价格高于MA20的股票数量: %d" % df_bias.sum().iloc[0])
        
        # ==================== 步骤3：获取股票行业分类 ====================
        log.info("-" * 50)
        log.info("[步骤3] 获取股票行业分类")
        
        s_stk_2_ind = getStockIndustry(p_stocks=initial_list, 
                                        p_industries_type=p_industries_type, 
                                        p_day=yesterday)
        
        log.info("[步骤3] 成功获取行业分类的股票数: %d" % len(s_stk_2_ind))
        
        # 添加行业代码列
        df_bias['industry_code'] = s_stk_2_ind
        
        # ==================== 步骤4：计算各行业宽度比例 ====================
        log.info("-" * 50)
        log.info("[步骤4] 计算各行业宽度比例")
        
        # 行业宽度比例 = 行业内高于MA20的股票数 / 行业内总股票数 * 100
        df_ratio = ((df_bias.groupby('industry_code').sum() * 100.0) / 
                    df_bias.groupby('industry_code').count()).round()
        
        log.info("[步骤4] 行业数量: %d" % len(df_ratio))
        log.info("[步骤4] 行业宽度数据（前10行）:")
        for i, (code, row) in enumerate(df_ratio.head(10).iterrows()):
            ind_name = SW1.get(code, '未知行业')
            log.info("  %s (%s): %.0f%%" % (code, ind_name, row.iloc[0]))
        
        # ==================== 步骤5：判断搅屎棍是否领涨 ====================
        log.info("-" * 50)
        log.info("[步骤5] 判断搅屎棍是否领涨")
        
        # 取宽度最大的行业
        yesterday_date = datetime.date(yesterday.year, yesterday.month, yesterday.day)
        top_values = df_ratio[yesterday_date].nlargest(g.num)
        I = top_values.index.tolist()
        
        # 获取领涨行业名称
        name_list = [SW1.get(code, '未知') for code in I]
        log.info("[步骤5] 行业宽度最高的行业: %s -> %s" % (str(I), str(name_list)))
        log.info("[步骤5] 行业宽度值: %.0f%%" % top_values.iloc[0])
        
        # 计算全市场宽度
        market_breadth = np.array(df_ratio.sum(axis=0).mean())
        g.market_breadth = market_breadth
        log.info("[步骤5] 全市场宽度平均值: %.2f%%" % market_breadth)
        
        # ==================== 步骤6：检查搅屎棍 ====================
        log.info("-" * 50)
        log.info("[步骤6] 检查四大搅屎棍")
        
        log.info("[搅屎棍检查] 银行(801780): 是否在前列 = %s" % ('801780' in I))
        log.info("[搅屎棍检查] 有色金属(801050): 是否在前列 = %s" % ('801050' in I))
        log.info("[搅屎棍检查] 煤炭(801950): 是否在前列 = %s" % ('801950' in I))
        log.info("[搅屎棍检查] 钢铁(801040): 是否在前列 = %s" % ('801040' in I))
        
        # 判断是否需要空仓
        bastion_in_top = any([code in I for code in BASTION_CODES])
        g.bastion_in_top = bastion_in_top
        
        log.info("[择时判断] 搅屎棍是否领涨: %s" % bastion_in_top)
        
        # ==================== 步骤7：择时决策 ====================
        log.info("-" * 50)
        log.info("[步骤7] 择时决策")
        
        if not bastion_in_top:
            # 【开仓】搅屎棍不在前列，市场健康，买入小市值优质股
            log.info("[择时决策] ✅ 开仓信号：搅屎棍不领涨")
            g.market_state = "normal"
            
            # 选股流程
            L = select_small_cap_stocks(context)
            final_list = L
            
            log.info("[选股结果] 目标股票数量: %d" % len(final_list))
            if final_list:
                log.info("[选股结果] 目标股票列表: %s" % str(final_list))
        else:
            # 【空仓】搅屎棍领涨，市场避险，跑
            log.info("[择时决策] ❌ 空仓信号：搅屎棍领涨，跑！")
            g.market_state = "defense"
            final_list = []
            
            log.info("[选股结果] 目标股票数量: 0（空仓）")
    
    except Exception as e:
        log.error("[选股模块] 异常: %s" % str(e))
        import traceback
        log.error(traceback.format_exc())
        return []
    
    log.info("=" * 70)
    return final_list


def select_small_cap_stocks(context):
    """选股：小市值 + 高质量（ROE/ROA筛选）"""
    log.info("-" * 50)
    log.info("[选股-小市值] 开始")
    
    today = context.current_dt
    
    # ==================== 步骤A：获取股票池 ====================
    log.info("[选股-A] 获取深证100成分股")
    try:
        S_stocks = get_index_stocks('399101.XSHE', today)  # 深证100
        log.info("[选股-A] 深证100成分股数量: %d" % len(S_stocks))
    except Exception as e:
        log.error("[选股-A] 获取失败: %s" % str(e))
        return []
    
    # ==================== 步骤B：过滤股票 ====================
    log.info("[选股-B] 过滤股票")
    
    # B1: 过滤科创/北交/创业板
    stocks = filter_kcbj_stock(S_stocks)
    log.info("[选股-B1] 过滤科创/北交/创业板后: %d -> %d" % (len(S_stocks), len(stocks)))
    
    # B2: 过滤ST
    choice = filter_st_stock(stocks)
    log.info("[选股-B2] 过滤ST后: %d -> %d" % (len(stocks), len(choice)))
    
    # B3: 过滤次新股（375天内）
    choice = filter_new_stock(context, choice)
    log.info("[选股-B3] 过滤次新股后: %d -> %d" % (len(stocks), len(choice)))
    
    # ==================== 步骤C：财务筛选 ====================
    log.info("[选股-C] 财务筛选")
    log.info("[选股-C] 筛选条件: ROE > 15%, ROA > 10%")
    
    try:
        df = get_fundamentals(query(
            valuation.code,
        ).filter(
            valuation.code.in_(choice),
            indicator.roe > 0.15,   # ROE > 15%
            indicator.roa > 0.10,   # ROA > 10%
        ).order_by(
            valuation.market_cap.asc()  # 按市值升序（小市值优先）
        ).limit(g.stock_num))
        
        if df is None or df.empty:
            log.warning("[选股-C] 财务筛选后为空")
            return []
        
        BIG_stock_list = df.set_index('code').index.tolist()
        log.info("[选股-C] 财务筛选后数量: %d" % len(BIG_stock_list))
        log.info("[选股-C] 财务筛选结果: %s" % str(BIG_stock_list))
        
    except Exception as e:
        log.error("[选股-C] 财务数据获取失败: %s" % str(e))
        return []
    
    # ==================== 步骤D：状态过滤 ====================
    log.info("[选股-D] 状态过滤")
    
    # D1: 过滤停牌
    BIG_stock_list = filter_paused_stock(BIG_stock_list)
    log.info("[选股-D1] 过滤停牌后: %d" % len(BIG_stock_list))
    
    # D2: 过滤涨停（不能买入）
    BIG_stock_list = filter_limitup_stock(context, BIG_stock_list)
    log.info("[选股-D2] 过滤涨停后: %d" % len(BIG_stock_list))
    
    # D3: 过滤跌停（可以卖出但不能买入）
    L = filter_limitdown_stock(context, BIG_stock_list)
    log.info("[选股-D3] 过滤跌停后: %d" % len(L))
    
    log.info("[选股-小市值] 最终选股数量: %d" % len(L))
    if L:
        log.info("[选股-小市值] 最终选股列表: %s" % str(L))
    
    return L


# ============================================================
#                    调仓函数
# ============================================================

def weekly_adjustment(context):
    """每周一调仓"""
    log.info("=" * 70)
    log.info("=== 调仓执行（周一09:30）===")
    
    # ==================== 获取目标股票 ====================
    target_B = get_stock_list(context)
    target_set = set(target_B)
    
    log.info("[调仓] 目标股票数量: %d" % len(target_B))
    log.info("[调仓] 当前持仓数量: %d" % len(g.hold_list))
    log.info("[调仓] 昨日涨停数量: %d" % len(g.yesterday_HL_list))
    
    # ==================== 卖出阶段 ====================
    log.info("-" * 50)
    log.info("[调仓-卖出] 开始")
    
    sell_count = 0
    for stock in g.hold_list:
        # 不在目标列表 且 不是昨日涨停 → 卖出
        if (stock not in target_set) and (stock not in g.yesterday_HL_list):
            position = context.portfolio.positions[stock]
            if close_position(position):
                sell_count += 1
                log.info("[卖出] %s: 成功卖出" % stock)
    
    log.info("[调仓-卖出] 卖出数量: %d" % sell_count)
    
    # ==================== 买入阶段 ====================
    log.info("-" * 50)
    log.info("[调仓-买入] 开始")
    
    position_count = len(context.portfolio.positions)
    target_num = len(target_B)
    
    log.info("[调仓-买入] 当前持仓: %d, 目标数量: %d" % (position_count, target_num))
    
    buy_count = 0
    if target_num > position_count:
        buy_num = min(len(target_B), g.stock_num * g.num - position_count)
        value = context.portfolio.cash / buy_num
        
        log.info("[调仓-买入] 需买入: %d, 每只金额: %.2f" % (buy_num, value))
        
        for stock in target_B:
            if stock not in list(context.portfolio.positions.keys()):
                if open_position(stock, value):
                    buy_count += 1
                    log.info("[买入] %s: 成功买入, 金额=%.2f" % (stock, value))
                    if len(context.portfolio.positions) == target_num:
                        break
    
    log.info("[调仓-买入] 买入数量: %d" % buy_count)
    log.info("=" * 70)


def check_limit_up(context):
    """每日14:00检查涨停股"""
    log.info("-" * 50)
    log.info("[涨停检查] 14:00")
    
    now_time = context.current_dt
    
    if not g.yesterday_HL_list:
        log.info("[涨停检查] 无昨日涨停股票，跳过")
        return
    
    log.info("[涨停检查] 检查股票数量: %d" % len(g.yesterday_HL_list))
    
    for stock in g.yesterday_HL_list:
        try:
            current_data = get_price(stock, end_date=now_time, frequency='1m', 
                                       fields=['close', 'high_limit'],
                                       skip_paused=False, fq='pre', count=1, 
                                       panel=False, fill_paused=True)
            
            current_close = current_data.iloc[0, 0]
            high_limit = current_data.iloc[0, 1]
            
            log.info("[涨停检查] %s: 当前价=%.2f, 涨停价=%.2f, 是否涨停=%s" 
                     % (stock, current_close, high_limit, current_close >= high_limit * 0.995))
            
            if current_close < high_limit * 0.995:
                # 涨停打开，卖出
                log.info("[涨停打开] %s: 涨停打开，卖出" % stock)
                position = context.portfolio.positions[stock]
                close_position(position)
            else:
                # 继续涨停，持有
                log.info("[继续涨停] %s: 继续涨停，持有" % stock)
                
        except Exception as e:
            log.error("[涨停检查] %s 异常: %s" % (stock, str(e)))


# ============================================================
#                    交易函数
# ============================================================

def order_target_value_(security, value):
    """自定义下单函数"""
    if value == 0:
        log.info("[下单] 卖出 %s" % security)
    else:
        log.info("[下单] 买入 %s 目标金额 %.2f" % (security, value))
    return order_target_value(security, value)


def open_position(security, value):
    """开仓函数"""
    order = order_target_value_(security, value)
    if order is not None and order.filled > 0:
        log.info("[开仓] %s 成功，成交数量: %d" % (security, order.filled))
        return True
    log.warning("[开仓] %s 失败" % security)
    return False


def close_position(position):
    """平仓函数"""
    security = position.security
    order = order_target_value_(security, 0)
    if order is not None:
        if order.status == OrderStatus.held and order.filled == order.amount:
            log.info("[平仓] %s 成功" % security)
            return True
    log.warning("[平仓] %s 失败（可能停牌）" % security)
    return False


# ============================================================
#                    过滤函数
# ============================================================

def filter_paused_stock(stock_list):
    """过滤停牌股票"""
    current_data = get_current_data()
    result = [stock for stock in stock_list if not current_data[stock].paused]
    return result


def filter_st_stock(stock_list):
    """过滤ST及其他具有退市标签的股票"""
    current_data = get_current_data()
    result = [stock for stock in stock_list
              if not current_data[stock].is_st
              and 'ST' not in current_data[stock].name
              and '*' not in current_data[stock].name
              and '退' not in current_data[stock].name]
    return result


def filter_kcbj_stock(stock_list):
    """过滤科创北交股票"""
    result = []
    for stock in stock_list:
        # 科创板: 68开头
        # 北交所: 4或8开头
        # 创业板: 3开头
        if stock[0] == '4' or stock[0] == '8' or stock[:2] == '68' or stock[0] == '3':
            continue
        result.append(stock)
    return result


def filter_limitup_stock(context, stock_list):
    """过滤涨停的股票"""
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    result = [stock for stock in stock_list 
              if stock in context.portfolio.positions.keys()
              or last_prices[stock][-1] < current_data[stock].high_limit]
    return result


def filter_limitdown_stock(context, stock_list):
    """过滤跌停的股票"""
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    result = [stock for stock in stock_list 
              if stock in context.portfolio.positions.keys()
              or last_prices[stock][-1] > current_data[stock].low_limit]
    return result


def filter_new_stock(context, stock_list):
    """过滤次新股（375天内上市的）"""
    yesterday = context.previous_date
    result = [stock for stock in stock_list
              if not yesterday - get_security_info(stock).start_date < datetime.timedelta(days=375)]
    return result


# ============================================================
#                    辅助函数
# ============================================================

def getStockIndustry(p_stocks, p_industries_type, p_day):
    """获取股票的行业分类"""
    dict_stk_2_ind = {}
    stocks_industry_dict = get_industry(p_stocks, date=p_day)
    for stock in stocks_industry_dict:
        if p_industries_type in stocks_industry_dict[stock]:
            dict_stk_2_ind[stock] = stocks_industry_dict[stock][p_industries_type]['industry_code']
    return pd.Series(dict_stk_2_ind)


def industry(stockList, industry_code, date):
    """计算每个行业的股票数量"""
    i_Constituent_Stocks = {}
    for i in industry_code:
        temp = get_industry_stocks(i, date)
        i_Constituent_Stocks[i] = list(set(temp).intersection(set(stockList)))
    
    count_dict = {}
    for name, content_list in i_Constituent_Stocks.items():
        count_dict[name] = len(content_list)
    return count_dict


# ============================================================
#                    盘后处理
# ============================================================

def after_trading_end(context):
    """盘后处理"""
    log.info("=" * 70)
    log.info("=== 盘后处理 ===")
    log.info("[日期] %s" % context.current_dt.strftime('%Y-%m-%d'))
    
    # 持仓统计
    positions = context.portfolio.positions
    hold_count = len([p for p in positions.values() if p.total_amount > 0])
    
    log.info("[盘后] 持仓数量: %d" % hold_count)
    log.info("[盘后] 总资产: %.2f" % context.portfolio.total_value)
    log.info("[盘后] 现金: %.2f" % context.portfolio.cash)
    log.info("[盘后] 市场状态: %s" % g.market_state)
    log.info("[盘后] 搅屎棍领涨: %s" % g.bastion_in_top)
    log.info("[盘后] 全市场宽度: %.2f%%" % g.market_breadth)
    
    # 打印持仓详情
    for code, pos in positions.items():
        if pos.total_amount > 0:
            # 聚宽用 pos.value（持仓市值），不是 pos.market_value
            market_value = pos.value if hasattr(pos, 'value') else pos.total_amount * pos.price
            log.info("  %s: 数量=%d, 市值=%.2f" % (code, pos.total_amount, market_value))
    
    log.info("=" * 70)