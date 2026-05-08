# ETF轮动策略 v2.1 - PTrade版本
# ==============================
#
# 【策略概述】
# 基于动量效应选择ETF，通过EPO优化权重降低风险
#
# 【交易规则】
# - 调仓周期：每月初
# - 持仓数量：3只（动量得分>0的前3只）
# - 权重分配：EPO优化
# - 交易时间：14:40之前的任意时间（先卖出，下一分钟买入）
#
# 【PTrade适配要点】
# 1. 复权参数：get_history 必须指定 fq='pre'
# 2. 股票代码：上海.SS，深圳.SZ
# 3. 灵活调仓：只要在14:40之前启动，当天就会执行调仓
# 4. 分步执行：第一分钟卖出，第二分钟买入
# 5. 拆单处理：买卖都支持拆单，单笔最大90万股
# 6. 涨停检查：涨停时跳过买入
#
# ==============================

import numpy as np
import pandas as pd
import math
from scipy.linalg import solve


# ============ 初始化函数 ============
def initialize(context):
    # ETF池（PTrade代码格式：.SS/.SZ）
    g.etf_pool = [
        # 商品
        '518880.SS',  # 黄金ETF
        '159985.SZ',  # 豆粕ETF
        # 海外
        '513100.SS',  # 纳指ETF
        # 宽基
        '510300.SS',  # 沪深300ETF
        '159915.SZ',  # 创业板
        # 窄基
        '159992.SZ',  # 创新药ETF
        '515700.SS',  # 新能车ETF
        '510150.SS',  # 消费ETF
        '515790.SS',  # 光伏ETF
        '515880.SS',  # 通信ETF
        '512720.SS',  # 计算机ETF
        '512660.SS',  # 军工ETF
        '159740.SZ',  # 恒生科技ETF
    ]
    
    # 设置股票池
    set_universe(g.etf_pool)
    
    # 设置基准
    set_benchmark('000300.XSHG')
    
    # 策略参数
    g.stock_num = 3
    g.m_days = 34
    g._lambda = 10
    g.w = 0.2
    
    # 调仓控制
    g.last_trade_month = -1
    g.trade_done_today = False
    g.sell_done = False
    g.buy_done = False
    
    # 目标ETF信息
    g.target_etfs = []
    g.target_weights = []
    g.etf_weight_map = {}
    
    # 回测设置
    if not is_trade():
        set_backtest()
    
    log.info("=== 策略初始化完成 ===")


# ============ 设置回测条件 ============
def set_backtest():
    set_limit_mode('UNLIMITED')
    set_commission(commission_ratio=0.0002, min_commission=5.0)
    set_slippage(slippage=0.002)


# ============ 盘前处理 ============
def before_trading_start(context, data):
    g.current_date = context.blotter.current_dt.strftime('%Y-%m-%d')
    g.trade_done_today = False
    g.sell_done = False
    g.buy_done = False
    g.target_etfs = []
    g.target_weights = []
    g.etf_weight_map = {}
    log.info("=== 盘前处理 日期: %s ===" % (g.current_date))


# ============ 盘中处理 ============
def handle_data(context, data):
    current_time = context.blotter.current_dt.strftime('%H:%M')
    current_month = context.blotter.current_dt.month
    
    # ==================== 调仓判断 ====================
    if current_month != g.last_trade_month and current_time < '14:40' and not g.trade_done_today:
        
        # ========== 阶段1：卖出（第一分钟） ==========
        if not g.sell_done:
            log.info("=" * 50)
            log.info("=== 月初调仓 ===")
            log.info("时间: %s" % current_time)
            
            # 获取当前持仓
            positions = get_positions()
            hold_list = list(positions.keys()) if positions else []
            
            # 计算目标ETF
            target_list = get_rank(g.etf_pool)
            if not target_list:
                log.warning("无法获取目标ETF，跳过调仓")
                g.last_trade_month = current_month
                g.trade_done_today = True
                return
            
            result = run_optimization(target_list)
            if not result:
                log.warning("无法计算权重，跳过调仓")
                g.last_trade_month = current_month
                g.trade_done_today = True
                return
            
            g.target_etfs = target_list
            g.target_weights = result['weights']
            g.etf_weight_map = {etf: g.target_weights[i] for i, etf in enumerate(g.target_etfs)}
            
            total_value = context.portfolio.total_value
            cash = context.portfolio.cash
            
            # 打印调仓计划
            log.info("=== 调仓计划 ===")
            log.info("总资产: %.2f, 现金: %.2f, 持仓市值: %.2f" % (total_value, cash, total_value - cash))
            log.info("--- 目标ETF及权重 ---")
            for i, etf in enumerate(g.target_etfs):
                w = g.target_weights[i]
                target_amt = total_value * w
                log.info("  %s: 权重=%.2f%%, 目标金额=%.2f" % (etf, w * 100, target_amt))
            
            log.info("--- 当前持仓 ---")
            for etf in hold_list:
                try:
                    pos = get_position(etf)
                    if pos and pos.amount > 0:
                        log.info("  %s: 持仓=%d股" % (etf, pos.amount))
                except:
                    pass
            log.info("=" * 50)
            
            # 执行卖出（带拆单）
            log.info("=== 卖出阶段 ===")
            for etf in hold_list:
                try:
                    pos = get_position(etf)
                    if not pos or pos.amount <= 0:
                        continue
                    
                    etf_converted = etf.replace('.XSHG', '.SS').replace('.XSHE', '.SZ')
                    weight = g.etf_weight_map.get(etf_converted, 0)
                    
                    # 计算目标股数
                    if weight <= 0 or etf_converted not in g.target_etfs:
                        # 清仓：全部卖出
                        sell_shares = pos.amount
                        log.info("[卖出] %s: 清仓 %d 股" % (etf, sell_shares))
                    else:
                        # 减仓：计算目标股数
                        try:
                            his = get_history(1, frequency='1d', field='close', security_list=etf, fq='pre', include=False, is_dict=True)
                            price = his[etf]['close'][-1] if his and etf in his else 0
                            if price > 0:
                                target_shares = int(total_value * weight / price / 100) * 100
                                if pos.amount > target_shares:
                                    sell_shares = pos.amount - target_shares
                                    log.info("[卖出] %s: 减仓 %d 股 (当前=%d, 目标=%d)" % (etf, sell_shares, pos.amount, target_shares))
                                else:
                                    sell_shares = 0
                            else:
                                sell_shares = 0
                        except:
                            sell_shares = 0
                    
                    # 拆单卖出
                    if sell_shares > 0:
                        remaining = sell_shares
                        while remaining > 0:
                            batch = min(remaining, 900000)  # 单笔最大90万股
                            batch = int(batch / 100) * 100
                            if batch > 0:
                                order(etf, -batch)
                                remaining -= batch
                            else:
                                if remaining > 0:
                                    order(etf, -remaining)  # 剩余不足100股，一次卖出
                                break
                            
                except Exception as e:
                    log.error("[卖出] %s 异常: %s" % (etf, str(e)))
            
            g.sell_done = True
            return
        
        # ========== 阶段2：买入（第二分钟） ==========
        if g.sell_done and not g.buy_done:
            log.info("=== 买入阶段 ===")
            log.info("总资产: %.2f, 可用资金: %.2f" % (context.portfolio.total_value, context.portfolio.cash))
            
            total_value = context.portfolio.total_value
            cash = context.portfolio.cash
            
            for i, etf in enumerate(g.target_etfs):
                w = g.target_weights[i]
                if w <= 0:
                    continue
                
                target_value = total_value * w
                
                # 获取当前持仓
                try:
                    pos = get_position(etf)
                    current_shares = pos.amount if pos else 0
                except:
                    current_shares = 0
                
                # 涨停检查
                skip_buy = False
                price = 0
                try:
                    his2 = get_history(2, frequency='1d', field='close', security_list=etf, fq='pre', include=False, is_dict=True)
                    if his2 and etf in his2 and len(his2[etf]['close']) >= 2:
                        yesterday_close = his2[etf]['close'][-2]
                        today_close = his2[etf]['close'][-1]
                        price = today_close
                        
                        code = etf.split('.')[0]
                        limit_rate = 0.20 if code.startswith('688') or code.startswith('300') else 0.10
                        
                        up_limit = yesterday_close * (1 + limit_rate)
                        
                        if today_close >= up_limit * 0.995:
                            skip_buy = True
                            log.warning("[买入] %s 涨停中，跳过" % etf)
                except Exception as e:
                    log.error("[风控] %s 检查异常: %s" % (etf, str(e)))
                
                if skip_buy:
                    continue
                
                # 计算目标股数
                if price > 0:
                    target_shares = int(target_value / price / 100) * 100
                    need_buy = target_shares - current_shares
                else:
                    need_buy = 0
                
                if need_buy <= 0:
                    log.info("[买入] %s: 当前=%d股, 目标=%d股, 无需买入" % (etf, current_shares, target_shares if price > 0 else 0))
                    continue
                
                log.info("[买入] %s: 当前=%d股, 目标=%d股, 需买入=%d股, 价格=%.2f" % 
                         (etf, current_shares, target_shares, need_buy, price))
                
                # 计算可用资金能买多少
                max_shares_by_cash = int(cash / price / 100) * 100 if price > 0 else 0
                actual_buy = min(need_buy, max_shares_by_cash)
                
                if actual_buy < 100:
                    log.warning("[买入] %s: 资金不足，跳过 (可用=%.2f)" % (etf, cash))
                    continue
                
                # 拆单买入
                remaining = actual_buy
                order_count = 0
                while remaining > 0:
                    batch = min(remaining, 900000)  # 单笔最大90万股
                    batch = int(batch / 100) * 100
                    if batch > 0:
                        order(etf, batch)
                        order_count += 1
                        remaining -= batch
                    else:
                        break
                
                log.info("[买入] %s: 下单 %d 笔，共 %d 股" % (etf, order_count, actual_buy))
                
                # 更新剩余资金
                cash -= actual_buy * price
            
            g.buy_done = True
            g.trade_done_today = True
            g.last_trade_month = current_month
            log.info("=== 买入完成 ===")
            log.info("=== 调仓完成 ===")


# ============ 动量因子计算 ============
def get_rank(etf_pool):
    """基于年化收益和判定系数打分的动量因子轮动"""
    score_list = []
    
    for etf in etf_pool:
        his = get_history(g.m_days, frequency='1d', field='close', 
                          security_list=etf, fq='pre', include=False, is_dict=True)
        
        if his is None or etf not in his:
            continue
        
        close_array = his[etf]['close']
        
        if len(close_array) < g.m_days:
            continue
        
        # 计算动量得分
        y = np.log(close_array)
        x = np.arange(len(y))
        slope, intercept = np.polyfit(x, y, 1)
        annualized_returns = math.pow(math.exp(slope), 250) - 1
        r_squared = 1 - (sum((y - (slope * x + intercept))**2) / ((len(y) - 1) * np.var(y, ddof=1)))
        score = annualized_returns * r_squared
        score_list.append({'etf': etf, 'score': score})
    
    # 排序
    df = pd.DataFrame(score_list)
    if df.empty:
        return []
    
    df = df.sort_values(by='score', ascending=False)
    
    # 筛选得分>0的
    filtered_list = df[df['score'] > 0]['etf'].tolist()[:g.stock_num]
    return filtered_list


# ============ EPO优化函数 ============
def epo(x, signal, lambda_, method='simple', w=None, anchor=None, normalize=True, endogenous=True):
    """EPO权重优化"""
    n = x.shape[1]
    
    vcov = x.cov()
    corr = x.corr()
    
    I = np.eye(n)
    V = np.zeros((n, n))
    np.fill_diagonal(V, vcov.values.diagonal())
    std = np.sqrt(V)
    
    s = signal.values if hasattr(signal, 'values') else signal
    a = anchor.values if hasattr(anchor, 'values') else anchor

    shrunk_cor = ((1 - w) * I @ corr.values) + (w * I)
    cov_tilde = std @ shrunk_cor @ std
    inv_shrunk_cov = solve(cov_tilde, np.eye(n))

    if method == 'simple':
        epo_weights = (1 / lambda_) * inv_shrunk_cov @ s
    elif method == 'anchored':
        if endogenous:
            num = np.sqrt(a.T @ cov_tilde @ a)
            denom = np.sqrt(s.T @ inv_shrunk_cov @ cov_tilde @ inv_shrunk_cov @ s)
            gamma = num / denom
            
            term1 = (1 - w) * gamma * s
            term2 = w * I @ V @ a
            
            combined = term1 + term2
            
            epo_weights = inv_shrunk_cov @ combined
        else:
            epo_weights = inv_shrunk_cov @ (((1 - w) * (1 / lambda_) * s) + ((w * I @ V @ a)))

    if normalize:
        epo_weights = [0 if weight < 0 else weight for weight in epo_weights]
        epo_weights = np.array(epo_weights) / np.sum(epo_weights)

    return epo_weights


# ============ 安全卖出函数（全部卖出） ============
def safe_sell(stock, max_shares=900000):
    """
    安全卖出函数：卖出全部持仓，支持拆单
    
    参数：
    - stock: 股票代码
    - max_shares: 单笔最大股数
    """
    try:
        pos = get_position(stock)
        if not pos or pos.amount <= 0:
            log.info("[卖出] %s 无持仓，跳过" % stock)
            return
        
        total_shares = pos.amount
        
        log.info("[卖出] %s 全部卖出 %d 股, 单笔上限: %d" % (stock, total_shares, max_shares))
        
        # 拆单卖出
        remaining = total_shares
        while remaining > 0:
            shares = min(remaining, max_shares)
            shares = int(shares / 100) * 100
            if shares > 0:
                order(stock, -shares)
                log.info("[卖出] %s 卖出 %d 股" % (stock, shares))
                remaining -= shares
            else:
                # 剩余不足100股，一次性卖出
                if remaining > 0:
                    order(stock, -remaining)
                    log.info("[卖出] %s 卖出剩余 %d 股" % (stock, remaining))
                break
                
    except Exception as e:
        log.error("[卖出] %s 卖出失败: %s" % (stock, str(e)))


# ============ 获取数据并调用优化 ============
def run_optimization(stocks):
    """获取数据并调用EPO优化"""
    # 获取价格数据（前复权）
    his = get_history(1200, frequency='1d', field='close', 
                      security_list=stocks, fq='pre', include=False, is_dict=True)
    
    if his is None:
        log.error("获取价格数据失败")
        return None
    
    # 构建DataFrame
    close_data = {}
    for etf in stocks:
        if etf in his:
            close_data[etf] = his[etf]['close']
    
    if not close_data:
        log.error("无有效价格数据")
        return None
    
    # 找到最短长度，对齐数据
    min_len = min(len(arr) for arr in close_data.values())
    
    # 对齐所有数组到相同长度
    close_data_aligned = {}
    for etf, arr in close_data.items():
        close_data_aligned[etf] = arr[-min_len:]
    
    close_prices = pd.DataFrame(close_data_aligned)
    
    # 按列名排序（与聚宽pivot行为一致）
    close_prices = close_prices.reindex(sorted(close_prices.columns), axis=1)
    
    # 计算收益率
    returns = close_prices.pct_change().dropna()
    
    # 计算锚定权重
    d = np.diag(returns.cov())
    a = (1/d) / (1/d).sum()
    
    # 调用EPO
    try:
        weights = epo(x=returns, signal=returns.mean(), lambda_=g._lambda, method='anchored', w=g.w, anchor=a)
        return {'weights': weights, 'columns': list(close_prices.columns)}
    except Exception as e:
        log.error("EPO优化失败: %s" % (str(e)))
        return None


# ============ 拆单函数 ============
def split_order(stock, target_value, max_shares=900000):
    """
    拆单函数：将大单拆成多笔小单
    
    参数：
    - stock: 股票代码
    - target_value: 目标金额
    - max_shares: 单笔最大股数（默认90万股，留10%安全边际）
    
    返回：
    - 订单列表 [{'stock': xxx, 'shares': xxx}, ...]
    """
    orders = []
    
    if target_value <= 0:
        return orders
    
    # 获取当前价格
    try:
        his = get_history(1, frequency='1d', field='close', security_list=stock, fq='pre', include=False, is_dict=True)
        if his is None or stock not in his:
            log.warning("[拆单] 无法获取 %s 价格" % stock)
            return orders
        
        price = his[stock]['close'][-1]
        if price <= 0:
            log.warning("[拆单] %s 价格无效: %.2f" % (stock, price))
            return orders
        
        # 计算目标股数（向下取整到100股）
        total_shares = int(target_value / price / 100) * 100
        
        if total_shares <= 0:
            log.info("[拆单] %s 目标股数为0，跳过" % stock)
            return orders
        
        log.info("[拆单] %s 目标股数: %d, 单笔上限: %d" % (stock, total_shares, max_shares))
        
        # 拆单
        remaining = total_shares
        while remaining > 0:
            shares = min(remaining, max_shares)
            # 向下取整到100股
            shares = int(shares / 100) * 100
            if shares > 0:
                orders.append({'stock': stock, 'shares': shares})
                remaining -= shares
            else:
                break
        
        log.info("[拆单] %s 拆分成 %d 笔订单" % (stock, len(orders)))
        
    except Exception as e:
        log.error("[拆单] %s 异常: %s" % (stock, str(e)))
    
    return orders


# ============ 卖出阶段 ============
def trade_sell(context, data):
    """调仓卖出阶段 - 在09:31执行所有卖出操作"""
    # 获取目标ETF
    target_list = get_rank(g.etf_pool)
    
    if not target_list:
        return
    
    # 获取当前持仓
    positions = get_positions()
    hold_list = list(positions.keys()) if positions else []
    
    # 计算权重
    result = run_optimization(target_list)
    
    if result is None:
        return
    
    weights = result['weights']
    
    # 保存目标信息供买入阶段使用
    g.target_etfs = target_list
    g.target_weights = weights
    
    # 建立ETF到权重的映射
    etf_weight_map = {}
    for i, etf in enumerate(target_list):
        etf_weight_map[etf] = weights[i]
    
    # ==================== 打印调仓信息 ====================
    total_value = context.portfolio.total_value
    cash = context.portfolio.cash
    
    log.info("=" * 50)
    log.info("=== 调仓计划 ===")
    log.info("总资产: %.2f, 现金: %.2f, 持仓市值: %.2f" % (total_value, cash, total_value - cash))
    log.info("--- 目标ETF及权重 ---")
    
    for i, etf in enumerate(target_list):
        w = weights[i]
        target_value = total_value * w
        log.info("  %s: 权重=%.2f%%, 目标金额=%.2f" % (etf, w * 100, target_value))
    
    log.info("--- 当前持仓 ---")
    for etf in hold_list:
        try:
            pos = get_position(etf)
            if pos and pos.amount > 0:
                log.info("  %s: 持仓=%d股" % (etf, pos.amount))
        except:
            pass
    
    log.info("=" * 50)
    
    # ==================== 卖出阶段：执行卖出 ====================
    log.info("=== 卖出阶段 ===")
    
    for etf in hold_list:
        # 转换代码格式
        etf_converted = etf.replace('.XSHG', '.SS').replace('.XSHE', '.SZ')
        
        # 获取当前持仓
        try:
            pos = get_position(etf)
            current_shares = pos.amount if pos else 0
        except:
            current_shares = 0
        
        if current_shares <= 0:
            continue
        
        # 计算目标金额
        if etf_converted not in target_list:
            # 不在目标池中，清仓
            target_value = 0
            log.info("[卖出] %s 不在目标池，清仓" % etf)
        else:
            weight = etf_weight_map.get(etf_converted, 0)
            target_value = total_value * weight
            
            if target_value <= 0:
                log.info("[卖出] %s 权重为0，清仓" % etf)
            else:
                log.info("[卖出] %s 目标金额=%.2f元" % (etf, target_value))
        
        # 使用目标金额下单（会自动卖出多余部分）
        order_target_value(etf, target_value)
    
    log.info("=== 卖出完成，等待买入 ===")


# ============ 买入阶段 ============
def trade_buy(context, data):
    """调仓买入阶段 - 使用目标金额下单"""
    if len(g.target_etfs) == 0 or len(g.target_weights) == 0:
        log.warning("[买入] 无目标ETF信息")
        return
    
    target_list = g.target_etfs
    weights = g.target_weights
    
    total_value = context.portfolio.total_value
    
    log.info("=== 买入阶段 ===")
    log.info("总资产: %.2f" % total_value)
    
    # ==================== 逐个买入目标ETF ====================
    for i, etf in enumerate(target_list):
        w = weights[i]
        
        if w <= 0:
            continue
        
        target_value = total_value * w
        
        # 风控检查
        skip_buy = False
        try:
            his2 = get_history(2, frequency='1d', field='close', security_list=etf, fq='pre', include=False, is_dict=True)
            if his2 and etf in his2 and len(his2[etf]['close']) >= 2:
                yesterday_close = his2[etf]['close'][-2]
                today_close = his2[etf]['close'][-1]
                
                code = etf.split('.')[0]
                limit_rate = 0.20 if code.startswith('688') or code.startswith('300') else 0.10
                
                up_limit = yesterday_close * (1 + limit_rate)
                down_limit = yesterday_close * (1 - limit_rate)
                
                if today_close >= up_limit * 0.995:
                    skip_buy = True
                    log.info("[风控] %s 涨停，跳过" % etf)
                if today_close <= down_limit * 1.005:
                    skip_buy = True
                    log.info("[风控] %s 跌停，跳过" % etf)
        except Exception as e:
            log.error("[风控] %s 检查异常: %s" % (etf, str(e)))
        
        if skip_buy:
            continue
        
        # 获取当前持仓
        try:
            pos = get_position(etf)
            current_shares = pos.amount if pos else 0
        except:
            current_shares = 0
        
        # 获取价格计算预计股数
        try:
            his = get_history(1, frequency='1d', field='close', security_list=etf, fq='pre', include=False, is_dict=True)
            price = his[etf]['close'][-1] if his and etf in his else 1.0
        except:
            price = 1.0
        
        expected_shares = int(target_value / price / 100) * 100
        
        log.info("[买入] %s: 目标=%.2f元, 预计%d股" % (etf, target_value, expected_shares))
        
        # 使用目标金额下单（PTrade会自动处理资金分配）
        order_target_value(etf, target_value)
    
    log.info("=== 买入完成 ===")
    
    g.target_etfs = []
    g.target_weights = []


# ============ 安全卖出函数（全部卖出） ============
def safe_sell_partial(stock, shares, max_shares=900000):
    """
    安全部分卖出函数：支持拆单
    
    参数：
    - stock: 股票代码
    - shares: 要卖出的股数
    - max_shares: 单笔最大股数
    """
    try:
        pos = get_position(stock)
        if not pos or pos.amount <= 0:
            return
        
        # 确保不超过持仓
        shares = min(shares, pos.amount)
        
        log.info("[卖出] %s 卖出 %d 股" % (stock, shares))
        
        # 拆单卖出
        remaining = shares
        while remaining > 0:
            sell_shares = min(remaining, max_shares)
            sell_shares = int(sell_shares / 100) * 100
            if sell_shares > 0:
                order(stock, -sell_shares)
                remaining -= sell_shares
            else:
                # 剩余不足100股，一次性卖出
                if remaining > 0:
                    order(stock, -remaining)
                break
                
    except Exception as e:
        log.error("[卖出] %s 卖出失败: %s" % (stock, str(e)))