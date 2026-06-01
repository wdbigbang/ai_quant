# ETF轮动策略 v3.0 - PTrade版本（定版）
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
# - 资金上限：g.capital_ratio 控制策略可用资金比例
#
# ==================== PTrade适配要点 ====================
#
# 1. 股票代码格式
#    - 上海：.SS（如 518880.SS）
#    - 深圳：.SZ（如 159915.SZ）
#    - 指数：.XBHS（如 399101.XBHS）
#
# 2. API使用准则（重要！）
#    - 交易时获取价格：data[etf].price（实盘最准确）
#    - 策略因子计算：get_history（动量、EPO等）
#    - 盘前预计算：get_history（复权因子、昨收价）
#
# 3. 复权处理
#    - data[etf].price 返回除权价格
#    - 前复权价格 = 除权价格 * 复权因子
#    - 复权因子 = 前复权价 / 除权价（盘前计算）
#
# 4. 下单方式
#    - 卖出：order(etf, -shares) 按股数，需拆单
#    - 买入：order_value(etf, value) 按金额
#
# 5. 拆单处理
#    - 单笔最大90万股（留10%安全边际）
#    - 卖出：按股数拆单
#    - 买入：order_value可能自动拆单，保险起见按金额拆单
#
# ==================== 踩坑记录 ====================
#
# 【坑1】交易时调用get_history
# - 问题：交易时用get_history获取价格，实盘可能不准确
# - 解决：用data[etf].price获取实时价格
#
# 【坑2】涨停判断需要昨收价
# - 问题：涨停价 = 昨收价 * (1+涨跌幅)，需要昨收价
# - 解决：盘前用get_history预存昨收价到g.yesterday_close
#
# 【坑3】复权价格问题
# - 问题：data[etf].price返回除权价，计算目标股数会不准确
# - 解决：盘前计算复权因子，交易时 data[etf].price * g.fq_factor
#
# 【坑4】资金上限需求
# - 问题：多策略并行时需要限制每个策略的资金使用
# - 解决：g.capital_ratio参数，目标金额 = 策略可用资金 * 权重
#
# ==================== 参数说明 ====================
#
# g.stock_num = 3          # 持仓数量
# g.m_days = 34            # 动量计算天数
# g._lambda = 10           # EPO风险厌恶系数
# g.w = 0.2                # EPO锚定权重
# g.capital_ratio = 1.0    # 策略可用资金比例（1.0=100%，0.5=50%）
#
# ==================== 文件信息 ====================
#
# 定版日期：2026-03-23
# 路径：D:\linux\ai_quant\quant_project\PtradeEgs\etf_rotation_strategy.py
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
    
    # ==================== 资金上限参数 ====================
    g.capital_ratio = 1.0  # 策略可用资金比例（1.0=100%，0.5=50%）
    log.info("[资金上限] 策略可用资金比例: %.0f%%" % (g.capital_ratio * 100))
    
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
    
    # ========== 盘前预计算（交易时不再调用get_history）==========
    # 1. 前复权因子：盘中用 data[etf].price * 因子 得到前复权价格
    # 2. 昨收价：用于涨停判断
    g.fq_factor = {}       # 前复权因子
    g.yesterday_close = {} # 昨天前复权收盘价（用于涨停判断）
    
    for etf in g.etf_pool:
        try:
            # 获取昨天的除权价格和前复权价格
            his_raw = get_history(1, frequency='1d', field='close', security_list=etf, fq=None, include=False, is_dict=True)
            raw_price = his_raw[etf]['close'][-1] if his_raw and etf in his_raw else 0
            
            his_fq = get_history(1, frequency='1d', field='close', security_list=etf, fq='pre', include=False, is_dict=True)
            fq_price = his_fq[etf]['close'][-1] if his_fq and etf in his_fq else 0
            
            if raw_price > 0 and fq_price > 0:
                g.fq_factor[etf] = fq_price / raw_price
                g.yesterday_close[etf] = fq_price  # 昨天前复权收盘价
                log.info("[盘前] %s: 除权价=%.3f, 前复权价=%.3f, 因子=%.4f" % (etf, raw_price, fq_price, g.fq_factor[etf]))
            else:
                g.fq_factor[etf] = 1.0
                g.yesterday_close[etf] = 0
                log.warning("[盘前] %s: 无法计算，使用默认因子1.0" % etf)
        except Exception as e:
            g.fq_factor[etf] = 1.0
            g.yesterday_close[etf] = 0
            log.error("[盘前] %s: 计算异常 %s" % (etf, str(e)))
    
    log.info("=== 盘前处理完成 日期: %s ===" % (g.current_date))


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
            
            # ==================== 资金上限计算 ====================
            strategy_capital = total_value * g.capital_ratio
            log.info("=" * 50)
            log.info("=== 调仓计划 ===")
            log.info("[资金上限] 总资产: %.2f, 资金比例: %.0f%%, 策略可用: %.2f" % (total_value, g.capital_ratio * 100, strategy_capital))
            log.info("现金: %.2f, 持仓市值: %.2f" % (cash, total_value - cash))
            log.info("--- 目标ETF及权重 ---")
            for i, etf in enumerate(g.target_etfs):
                w = g.target_weights[i]
                target_amt = strategy_capital * w  # 使用策略可用资金
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
                    
                    # ========== 使用 data[etf].price 获取前复权价格 ==========
                    raw_price = data[etf].price if hasattr(data[etf], 'price') else 0
                    fq_factor = g.fq_factor.get(etf, 1.0)
                    price = raw_price * fq_factor
                    
                    log.info("[卖出] %s: 实时价=%.3f, 复权因子=%.4f, 前复权价=%.3f" % (etf, raw_price, fq_factor, price))
                    
                    # 计算目标股数（使用策略可用资金）
                    if weight <= 0 or etf_converted not in g.target_etfs:
                        # 清仓：全部卖出
                        sell_shares = pos.amount
                        log.info("[卖出] %s: 清仓 %d 股（不在目标池）" % (etf, sell_shares))
                    elif price <= 0:
                        log.error("[卖出] %s 无法获取价格，跳过" % etf)
                        sell_shares = 0
                    else:
                        # 减仓：计算目标股数（基于策略可用资金）
                        target_shares = int(strategy_capital * weight / price / 100) * 100
                        log.info("[卖出] %s: 策略资金=%.2f, 权重=%.2f%%, 目标股数=%d" % (etf, strategy_capital, weight * 100, target_shares))
                        if pos.amount > target_shares:
                            sell_shares = pos.amount - target_shares
                            log.info("[卖出] %s: 减仓 %d 股 (当前=%d, 目标=%d)" % (etf, sell_shares, pos.amount, target_shares))
                        else:
                            sell_shares = 0
                            log.info("[卖出] %s: 无需减仓 (当前=%d <= 目标=%d)" % (etf, pos.amount, target_shares))
                    
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
            
            total_value = context.portfolio.total_value
            cash = context.portfolio.cash
            
            # ==================== 资金上限计算 ====================
            strategy_capital = total_value * g.capital_ratio
            log.info("[资金上限] 总资产: %.2f, 资金比例: %.0f%%, 策略可用: %.2f" % (total_value, g.capital_ratio * 100, strategy_capital))
            log.info("[资金上限] 当前现金: %.2f" % cash)
            
            for i, etf in enumerate(g.target_etfs):
                w = g.target_weights[i]
                if w <= 0:
                    continue
                
                # 目标金额 = 策略可用资金 * 权重
                target_value = strategy_capital * w
                
                # 获取当前持仓
                try:
                    pos = get_position(etf)
                    current_shares = pos.amount if pos else 0
                    current_value = pos.market_value if pos and hasattr(pos, 'market_value') else 0
                except:
                    current_shares = 0
                    current_value = 0
                
                # 涨停检查
                skip_buy = False
                price = 0
                yesterday_close = 0
                
                # ========== 使用盘前预存的昨收价，交易时不调用get_history ==========
                try:
                    # 获取实时价格（除权价）
                    raw_price = data[etf].price if hasattr(data[etf], 'price') else 0
                    
                    # 获取复权因子（盘前已计算）
                    fq_factor = g.fq_factor.get(etf, 1.0)
                    
                    # 计算前复权价格
                    price = raw_price * fq_factor
                    
                    # 获取昨收价（盘前已计算）
                    yesterday_close = g.yesterday_close.get(etf, 0)
                    
                    log.info("[买入] %s: 实时价=%.3f, 复权因子=%.4f, 前复权价=%.3f, 昨收=%.3f" 
                             % (etf, raw_price, fq_factor, price, yesterday_close))
                except Exception as e:
                    log.error("[买入] %s 获取价格异常: %s" % (etf, str(e)))
                
                if price <= 0:
                    log.error("[买入] %s 无法获取价格，跳过" % etf)
                    continue
                
                # 涨停判断
                try:
                    code = etf.split('.')[0]
                    limit_rate = 0.20 if code.startswith('688') or code.startswith('300') else 0.10
                    
                    up_limit = yesterday_close * (1 + limit_rate)
                    
                    log.info("[涨停判断] %s: 昨收=%.3f, 当前价=%.3f, 涨停价=%.3f, 涨停=%s" 
                             % (etf, yesterday_close, price, up_limit, price >= up_limit * 0.995))
                    
                    if price >= up_limit * 0.995:
                        skip_buy = True
                        log.warning("[买入] %s 涨停中，跳过" % etf)
                except Exception as e:
                    log.error("[风控] %s 涨停判断异常: %s" % (etf, str(e)))
                
                if skip_buy:
                    continue
                
                # 计算需要买入的金额
                need_buy_value = target_value - current_value
                
                log.info("[买入] %s: 权重=%.2f%%, 目标=%.2f元, 当前=%.2f元, 需买入=%.2f元" 
                         % (etf, w * 100, target_value, current_value, need_buy_value))
                
                if need_buy_value <= 100:
                    log.info("[买入] %s: 无需买入（差额<=100）" % etf)
                    continue
                
                log.info("[买入] %s: 当前=%.2f元, 目标=%.2f元, 需买入=%.2f元" % (etf, current_value, target_value, need_buy_value))
                
                # 实际买入金额（不超过可用资金）
                actual_buy_value = min(need_buy_value, cash)
                
                if actual_buy_value < 100:
                    log.warning("[买入] %s: 资金不足，跳过 (可用=%.2f)" % (etf, cash))
                    continue
                
                # 计算单笔最大金额（90万股 * 价格，留5%安全边际）
                max_value_per_order = 900000 * price * 0.95 if price > 0 else 500000
                
                # 拆单买入（按金额）
                remaining_value = actual_buy_value
                order_count = 0
                while remaining_value > 0:
                    batch_value = min(remaining_value, max_value_per_order)
                    if batch_value > 0:
                        order_value(etf, batch_value)
                        order_count += 1
                        remaining_value -= batch_value
                    else:
                        break
                
                log.info("[买入] %s: 下单 %d 笔，共 %.2f 元，剩余资金 %.2f" % (etf, order_count, actual_buy_value, cash - actual_buy_value))
                
                # 更新剩余资金
                cash -= actual_buy_value
            
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
