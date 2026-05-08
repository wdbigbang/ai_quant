# 行业哨兵策略（Sector Sentinel Strategy）v0.1 - PTrade版本（初始移植）
# ==============================
#
# 【策略概述】
# 通过监测"四大搅屎棍"（银行、有色、煤炭、钢铁）的行业宽度信号判断市场状态
# - 搅屎棍领涨 → 市场避险情绪强 → 空仓（跑）
# - 搅屎棍不领涨 → 市场正常 → 开仓买小市值优质股
#
# 【来源】
# - 聚宽文章：https://www.joinquant.com/post/49085
# - 作者：MarioC
# - 聚宽源码：D:\linux\ai_quant\quant_project\JoinQuantEgs\sector_sentinel_strategy.py
#
# 【PTrade移植要点】（v0.1）
# 1. run_daily/run_weekly → before_trading_start + handle_data 手动调度
# 2. get_industry/get_industry_stocks → PTrade API 需查找替代
# 3. 股票代码：.XSHG/.XSHE → .SS/.SZ，指数.XBHS
# 4. get_price → get_history（返回OrderedDict）
# 5. get_current_data() → data对象 + get_snapshot（实盘）
# 6. context.previous_date → 需手动计算
# 7. history() → get_history
#
# 【待确认】
# - PTrade行业分类API：get_industry?
# - 申万行业代码映射是否一致
# - 行业宽度计算所需的价格数据获取方式
#
# ==============================

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


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
    log.info("=== 行业哨兵策略 v0.1 初始化 ===")
    log.info("=" * 70)
    
    # ==================== 基本设置 ====================
    set_benchmark("000985.XBHS")  # 中证全指
    
    # ==================== 策略参数 ====================
    g.stock_num = 10        # 持仓数量
    g.num = 1               # 取涨幅最大的行业数量（只看第一名）
    
    # ==================== 调仓周期 ====================
    g.adjust_freq = 'weekly'  # 每周一调仓
    g.last_adjust_date = None  # 上次调仓日期
    
    # ==================== 持仓状态 ====================
    g.hold_list = []            # 当前持仓股票列表
    g.yesterday_HL_list = []    # 昨日涨停股票列表
    g.current_date = None       # 当前日期
    g.yesterday_date = None     # 昨日日期
    
    # ==================== 择时信号 ====================
    g.market_state = "normal"   # 市场状态：normal/defense
    g.bastion_in_top = False    # 搅屎棍是否在行业宽度前列
    g.market_breadth = 0        # 全市场宽度
    
    # ==================== 目标股票池 ====================
    g.target_stocks = []        # 目标买入股票列表
    g.handle_data_flag = False  # 是否允许交易
    
    # ==================== 昨收价（涨停检查用）====================
    g.yesterday_close = {}      # 昨收价
    g.yesterday_high_limit = {} # 昨日涨停价
    
    # ==================== 打印参数 ====================
    log.info("[参数] 持仓数量: %d" % g.stock_num)
    log.info("[参数] 行业数量(g.num): %d (只看第一名)" % g.num)
    log.info("[参数] 四大搅屎棍: %s" % str(BASTION_NAMES))
    log.info("=" * 70)


# ============================================================
#                    盘前准备函数
# ============================================================

def before_trading_start(context, data):
    """盘前准备：更新持仓列表、涨停列表、昨收价"""
    log.info("=" * 70)
    log.info("=== 盘前准备（09:05）===")
    
    # ==================== 更新日期 ====================
    today = context.current_dt
    g.current_date = today.strftime('%Y-%m-%d')
    
    # 计算昨日日期（PTrade没有previous_date，需手动计算）
    # 获取最近两个交易日
    trading_days = get_trading_days(2, end_date=today.strftime('%Y-%m-%d'))
    if len(trading_days) >= 2:
        g.yesterday_date = trading_days[-2]  # 昨日交易日
    else:
        g.yesterday_date = today.strftime('%Y-%m-%d')
    
    log.info("[日期] 今日: %s, 昨日: %s" % (g.current_date, g.yesterday_date))
    
    # ==================== 更新持仓列表 ====================
    g.hold_list = []
    positions = get_positions()
    for code, pos in positions.items():
        if pos.amount > 0:
            # PTrade代码格式转换（.SS/.SZ → .XSHG/.XSHE用于日志对比）
            g.hold_list.append(code)
    
    log.info("[持仓] 当前持仓数量: %d" % len(g.hold_list))
    if g.hold_list:
        log.info("[持仓] 持仓列表: %s" % str(g.hold_list))
    
    # ==================== 获取昨日涨停列表 ====================
    g.yesterday_HL_list = []
    g.yesterday_close = {}
    g.yesterday_high_limit = {}
    
    if g.hold_list:
        for stock in g.hold_list:
            try:
                # 获取昨日收盘价和涨停价
                his = get_history(1, frequency='1d', field='close', 
                                  security_list=stock, fq='pre', include=False, is_dict=True)
                if stock in his:
                    close_price = his[stock]['close'][-1]
                    g.yesterday_close[stock] = close_price
                    
                    # 计算涨停价（昨日收盘价 × 1.1）
                    # PTrade没有high_limit字段，需手动计算
                    high_limit = close_price * 1.1
                    g.yesterday_high_limit[stock] = high_limit
                    
                    # 判断昨日是否涨停（收盘价 ≈ 涨停价）
                    if abs(close_price - high_limit) / high_limit < 0.005:
                        g.yesterday_HL_list.append(stock)
                        log.info("[涨停] %s: 昨日涨停, 收盘=%.2f" % (stock, close_price))
                    
            except Exception as e:
                log.error("[涨停] %s 获取失败: %s" % (stock, str(e)))
        
        if g.yesterday_HL_list:
            log.info("[涨停] 昨日涨停股票: %s" % str(g.yesterday_HL_list))
        else:
            log.info("[涨停] 无昨日涨停股票")
    
    # ==================== 判断是否周一调仓 ====================
    weekday = today.weekday()  # 0=周一
    if weekday == 0:
        log.info("[调仓] 今日周一，触发调仓")
        g.handle_data_flag = True
        
        # 执行择时选股
        g.target_stocks = get_stock_list(context, data)
        log.info("[选股] 目标股票数量: %d" % len(g.target_stocks))
        if g.target_stocks:
            log.info("[选股] 目标股票列表: %s" % str(g.target_stocks))
    else:
        log.info("[调仓] 今日非周一，跳过调仓")
        g.handle_data_flag = False
        g.target_stocks = []
    
    log.info("=" * 70)


# ============================================================
#                    行业宽度计算（核心择时）- 待实现
# ============================================================

def get_stock_list(context, data):
    """
    核心选股模块：通过行业宽度判断市场状态
    
    【PTrade待实现】
    - 行业分类API：PTrade是否有get_industry?
    - 行业宽度计算：价格高于MA20的比例
    
    步骤：
    1. 计算各行业的宽度（多少股票高于20日均线）
    2. 判断搅屎棍是否在行业宽度前列
    3. 择时决策：搅屎棍领涨 → 空仓；不领涨 → 买入小市值
    """
    log.info("=" * 70)
    log.info("=== 选股模块（核心择时）===")
    log.info("[警告] 行业宽度计算待实现，暂时使用简化逻辑")
    
    # ==================== 步骤1：获取基准指数成分股 ====================
    log.info("-" * 50)
    log.info("[步骤1] 获取基准指数成分股")
    
    # PTrade指数代码：中证全指 000985.XBHS
    try:
        initial_list = get_index_stocks("000985.XBHS")
        log.info("[步骤1] 中证全指成分股数量: %d" % len(initial_list))
        log.info("[步骤1] 成分股样例（前5只）: %s" % str(initial_list[:5]))
    except Exception as e:
        log.error("[步骤1] 获取成分股失败: %s" % str(e))
        return []
    
    # ==================== 步骤2：行业宽度计算（待实现）====================
    log.info("-" * 50)
    log.info("[步骤2] 行业宽度计算（待实现）")
    log.info("[TODO] 需确认PTrade行业分类API")
    
    # 暂时跳过行业宽度计算，直接执行小市值选股
    # TODO: 实现行业宽度计算逻辑
    g.bastion_in_top = False  # 暂时假设搅屎棍不领涨
    g.market_state = "normal"
    
    # ==================== 步骤7：择时决策 ====================
    log.info("-" * 50)
    log.info("[步骤7] 择时决策")
    
    if not g.bastion_in_top:
        # 【开仓】搅屎棍不在前列，市场健康
        log.info("[择时决策] ✅ 开仓信号：搅屎棍不领涨")
        
        # 选股流程
        L = select_small_cap_stocks(context, data)
        return L
    else:
        # 【空仓】搅屎棍领涨，市场避险
        log.info("[择时决策] ❌ 空仓信号：搅屎棍领涨，跑！")
        g.market_state = "defense"
        return []


def select_small_cap_stocks(context, data):
    """选股：小市值 + 高质量（ROE/ROA筛选）"""
    log.info("-" * 50)
    log.info("[选股-小市值] 开始")
    
    today = context.current_dt
    
    # ==================== 步骤A：获取股票池 ====================
    log.info("[选股-A] 获取深证100成分股")
    
    # PTrade指数代码：深证100 399101.XBHS
    try:
        S_stocks = get_index_stocks("399101.XBHS")
        log.info("[选股-A] 深证100成分股数量: %d" % len(S_stocks))
    except Exception as e:
        log.error("[选股-A] 获取失败: %s" % str(e))
        return []
    
    # ==================== 步骤B：过滤股票 ====================
    log.info("[选股-B] 过滤股票")
    
    # B1: 过滤科创/北交/创业板
    stocks = filter_kcbj_stock(S_stocks)
    log.info("[选股-B1] 过滤科创/北交/创业板后: %d -> %d" % (len(S_stocks), len(stocks)))
    
    # B2: 过滤ST/停牌/退市
    stocks = filter_stock_by_status(stocks, filter_type=["ST", "HALT", "DELISTING"])
    log.info("[选股-B2] 过滤ST/停牌/退市后: %d -> %d" % (len(S_stocks), len(stocks)))
    
    # B3: 过滤次新股（375天内上市的）- 待实现
    # TODO: PTrade获取上市日期的API
    log.info("[选股-B3] 过滤次新股（暂未实现）")
    
    # ==================== 步骤C：财务筛选 ====================
    log.info("[选股-C] 财务筛选")
    log.info("[选股-C] 筛选条件: ROE > 15%, ROA > 10%")
    
    try:
        # PTrade用get_fundamentals获取财务数据
        df = get_fundamentals(stocks, "indicator", 
                              fields=["roe", "roa"], 
                              date=g.yesterday_date)
        
        if df is None or df.empty:
            log.warning("[选股-C] 财务数据为空")
            return []
        
        # 筛选条件
        df_filtered = df[(df['roe'] > 0.15) & (df['roa'] > 0.10)]
        
        if df_filtered.empty:
            log.warning("[选股-C] 财务筛选后为空")
            return []
        
        # 获取市值数据用于排序
        df_value = get_fundamentals(df_filtered['code'].tolist(), "valuation",
                                    fields=["market_cap"], 
                                    date=g.yesterday_date)
        
        if df_value is not None and not df_value.empty:
            df_filtered = df_filtered.merge(df_value, on='code')
            df_filtered = df_filtered.sort_values('market_cap', ascending=True)
        
        BIG_stock_list = df_filtered['code'].tolist()[:g.stock_num]
        
        log.info("[选股-C] 财务筛选后数量: %d" % len(BIG_stock_list))
        log.info("[选股-C] 财务筛选结果: %s" % str(BIG_stock_list))
        
    except Exception as e:
        log.error("[选股-C] 财务数据获取失败: %s" % str(e))
        return []
    
    # ==================== 步骤D：状态过滤 ====================
    log.info("[选股-D] 状态过滤")
    
    # D1: 过滤涨停（不能买入）
    BIG_stock_list = filter_limitup_stock(context, data, BIG_stock_list)
    log.info("[选股-D1] 过滤涨停后: %d" % len(BIG_stock_list))
    
    # D2: 过滤跌停（可以卖出但不能买入）
    BIG_stock_list = filter_limitdown_stock(context, data, BIG_stock_list)
    log.info("[选股-D2] 过滤跌停后: %d" % len(BIG_stock_list))
    
    log.info("[选股-小市值] 最终选股数量: %d" % len(BIG_stock_list))
    if BIG_stock_list:
        log.info("[选股-小市值] 最终选股列表: %s" % str(BIG_stock_list))
    
    return BIG_stock_list


# ============================================================
#                    调仓执行函数
# ============================================================

def handle_data(context, data):
    """交易执行：周一09:30调仓 + 14:00涨停检查"""
    
    current_time = context.current_dt.strftime('%H:%M')
    
    # ==================== 09:31 调仓执行 ====================
    if current_time == '09:31' and g.handle_data_flag:
        log.info("=" * 70)
        log.info("=== 调仓执行（周一09:31）===")
        
        target_B = g.target_stocks
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
                if close_position(context, data, stock):
                    sell_count += 1
                    log.info("[卖出] %s: 成功卖出" % stock)
        
        log.info("[调仓-卖出] 卖出数量: %d" % sell_count)
        
        # ==================== 买入阶段 ====================
        log.info("-" * 50)
        log.info("[调仓-买入] 开始")
        
        positions = get_positions()
        position_count = len([p for p in positions.values() if p.amount > 0])
        target_num = len(target_B)
        
        log.info("[调仓-买入] 当前持仓: %d, 目标数量: %d" % (position_count, target_num))
        
        buy_count = 0
        if target_num > position_count:
            cash = context.portfolio.cash
            buy_num = target_num - position_count
            value = cash / buy_num
            
            log.info("[调仓-买入] 需买入: %d, 每只金额: %.2f" % (buy_num, value))
            
            for stock in target_B:
                if stock not in positions or positions[stock].amount == 0:
                    if open_position(context, data, stock, value):
                        buy_count += 1
                        log.info("[买入] %s: 成功买入, 金额=%.2f" % (stock, value))
                        
                        positions = get_positions()
                        if len([p for p in positions.values() if p.amount > 0]) >= target_num:
                            break
        
        log.info("[调仓-买入] 买入数量: %d" % buy_count)
        log.info("=" * 70)
        
        g.handle_data_flag = False  # 防止重复执行
    
    # ==================== 14:00 涨停检查 ====================
    if current_time == '14:00' and g.yesterday_HL_list:
        log.info("-" * 50)
        log.info("[涨停检查] 14:00")
        
        for stock in g.yesterday_HL_list:
            try:
                # 获取当前价格
                if stock in data:
                    current_close = data[stock].price
                else:
                    # data中可能没有，用get_snapshot
                    snap = get_snapshot(stock)
                    current_close = snap.get('last', 0)
                
                # 涨停价（昨日收盘价 × 1.1）
                high_limit = g.yesterday_close.get(stock, 0) * 1.1
                
                log.info("[涨停检查] %s: 当前价=%.2f, 涨停价=%.2f" 
                         % (stock, current_close, high_limit))
                
                if current_close < high_limit * 0.995:
                    # 涨停打开，卖出
                    log.info("[涨停打开] %s: 涨停打开，卖出" % stock)
                    close_position(context, data, stock)
                else:
                    log.info("[继续涨停] %s: 继续涨停，持有" % stock)
                    
            except Exception as e:
                log.error("[涨停检查] %s 异常: %s" % (stock, str(e)))


# ============================================================
#                    交易函数
# ============================================================

def open_position(context, data, security, value):
    """开仓函数"""
    try:
        # 检查涨停
        if check_limit(security) == 1:
            log.warning("[开仓] %s 已涨停，跳过" % security)
            return False
        
        # PTrade用order_value下单
        order_value(security, value)
        log.info("[开仓] %s 成功，金额=%.2f" % (security, value))
        return True
    except Exception as e:
        log.error("[开仓] %s 失败: %s" % (security, str(e)))
        return False


def close_position(context, data, security):
    """平仓函数"""
    try:
        pos = get_position(security)
        if pos is None or pos.amount == 0:
            return False
        
        # 检查可卖数量（T+1）
        enable_amount = pos.enable_amount
        if enable_amount == 0:
            log.warning("[平仓] %s 无可卖数量（T+1限制）" % security)
            return False
        
        # PTrade用order_target卖出
        order_target(security, 0)
        log.info("[平仓] %s 成功" % security)
        return True
    except Exception as e:
        log.error("[平仓] %s 失败: %s" % (security, str(e)))
        return False


# ============================================================
#                    过滤函数
# ============================================================

def filter_kcbj_stock(stock_list):
    """过滤科创北交股票"""
    result = []
    for stock in stock_list:
        # PTrade代码格式：.SS/.SZ
        code = stock.split('.')[0]
        
        # 科创板: 68开头
        # 北交所: 4或8开头
        # 创业板: 3开头
        if code.startswith('4') or code.startswith('8') or code.startswith('68') or code.startswith('3'):
            continue
        result.append(stock)
    return result


def filter_limitup_stock(context, data, stock_list):
    """过滤涨停的股票"""
    result = []
    for stock in stock_list:
        if check_limit(stock) == 1:
            continue  # 涨停，跳过
        result.append(stock)
    return result


def filter_limitdown_stock(context, data, stock_list):
    """过滤跌停的股票"""
    result = []
    for stock in stock_list:
        if check_limit(stock) == -1:
            continue  # 跌停，跳过
        result.append(stock)
    return result


# ============================================================
#                    盘后处理
# ============================================================

def after_trading_end(context, data):
    """盘后处理"""
    log.info("=" * 70)
    log.info("=== 盘后处理 ===")
    log.info("[日期] %s" % g.current_date)
    
    # 持仓统计
    positions = get_positions()
    hold_count = len([p for p in positions.values() if p.amount > 0])
    
    log.info("[盘后] 持仓数量: %d" % hold_count)
    log.info("[盘后] 总资产: %.2f" % context.portfolio.total_value)
    log.info("[盘后] 现金: %.2f" % context.portfolio.cash)
    log.info("[盘后] 市场状态: %s" % g.market_state)
    log.info("[盘后] 搅屎棍领涨: %s" % g.bastion_in_top)
    
    # 打印持仓详情
    for code, pos in positions.items():
        if pos.amount > 0:
            market_value = pos.amount * pos.price
            log.info("  %s: 数量=%d, 市值=%.2f" % (code, pos.amount, market_value))
    
    log.info("=" * 70)