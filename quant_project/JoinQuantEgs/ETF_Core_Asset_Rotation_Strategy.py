# ETF核心资产轮动策略（安全摸狗策略）v1.1 - JoinQuant版本（详细日志）
# ==============================
#
# 【策略概述】
# 每日选择动量得分最高的1只ETF满仓持有，追求简单高效
#
# 【交易规则】
# - 调仓频率：每日09:30
# - 持仓数量：仅1只（动量得分最高且在安全区间内）
# - 动量计算：加权线性回归（25天，近期权重更大）
# - 打分公式：年化收益 × R²
# - 安全区过滤：score > 0 且 <= 5（避免追高风险）
#
# 【v1.1更新】
# - 添加详细日志输出（动量得分、安全区过滤、资金状况、买卖详情）
# - 作为PTrade对齐的基准参考
#
# ==================== 文件信息 ====================
#
# 版本：v1.1（详细日志版）
# 更新日期：2026-05-27
# 路径：D:\linux\ai_quant\quant_project\JoinQuantEgs\ETF_Core_Asset_Rotation_Strategy.py
#
# ==============================

import numpy as np
import pandas as pd
import math


# ============ 动量计算函数 ============
def MOM(etf):
    """加权线性回归动量计算

    使用加权线性回归计算年化收益，权重线性增加（近期权重更大）
    打分公式：年化收益 × R²（拟合优度）

    返回：score, annualized_returns, r_squared
    """
    df = attribute_history(etf, g.m_days, '1d', ['close'])

    close_arr = df['close'].values
    if len(close_arr) < g.m_days:
        log.warning("[MOM] %s: 数据不足（%d < %d）" % (etf, len(close_arr), g.m_days))
        return -999, 0, 0

    # 加权线性回归
    y = np.log(close_arr)
    n = len(y)
    x = np.arange(n)
    weights = np.linspace(1, 2, n)  # 线性增加权重（近期权重更大）

    slope, intercept = np.polyfit(x, y, 1, w=weights)
    annualized_returns = math.pow(math.exp(slope), 250) - 1

    # 计算R²（加权残差）
    residuals = y - (slope * x + intercept)
    weighted_residuals = weights * residuals**2
    r_squared = 1 - (np.sum(weighted_residuals) / np.sum(weights * (y - np.mean(y))**2))

    score = annualized_returns * r_squared

    return score, annualized_returns, r_squared


# ============ 选股函数 ============
def get_rank(etf_pool):
    """基于动量得分排序，安全区间过滤

    安全区过滤：score > 0 且 <= 5
    - score <= 0: 无动量，不值得持有
    - score > 5: 动量过高，追高风险太大

    返回：排名列表 [{'etf': code, 'score': value, 'annual_ret': value, 'r2': value}, ...]
    """
    log.info("=" * 60)
    log.info(">>> 动量计算（天数=%d）" % g.m_days)
    log.info("-" * 60)

    score_list = []

    for etf in etf_pool:
        score, annual_ret, r2 = MOM(etf)
        score_list.append({
            'etf': etf,
            'score': score,
            'annual_ret': annual_ret,
            'r2': r2
        })

        # 详细输出每个ETF的计算结果
        if score != -999:
            log.info("    [%s] 动量得分=%.4f | 年化收益=%.2f%% | R²=%.4f"
                     % (etf, score, annual_ret * 100, r2))
        else:
            log.warning("    [%s] 动量得分=无效（数据不足）" % etf)

    df = pd.DataFrame(score_list)

    # 排序（降序）
    df = df.sort_values(by='score', ascending=False)

    log.info("-" * 60)
    log.info(">>> 动量排名（降序）")
    for i, row in df.iterrows():
        if row['score'] != -999:
            log.info("    第%d名: [%s] 得分=%.4f" % (i+1, row['etf'], row['score']))

    # 安全区间过滤：score > 0 且 <= 5
    df_filtered = df[(df['score'] > 0) & (df['score'] <= 5)]

    log.info("-" * 60)
    log.info(">>> 安全区过滤（score > 0 且 <= 5）")

    if len(df_filtered) == 0:
        log.warning("    无符合条件ETF（全部得分<=0或>5）")
        log.info("    → 空仓观望")
        log.info("=" * 60)
        return []

    log.info("    符合条件%d只：" % len(df_filtered))
    for i, row in df_filtered.iterrows():
        log.info("      [%s] 得分=%.4f（安全区）" % (row['etf'], row['score']))

    log.info("=" * 60)

    # 返回完整信息（包含得分详情）
    return df_filtered.to_dict('records')


# ============ 初始化函数 ============
def initialize(context):
    # 设定基准
    set_benchmark('000300.XSHG')
    # 用真实价格交易
    set_option('use_real_price', True)
    # 打开防未来函数
    set_option("avoid_future_data", True)
    # 设置滑点
    set_slippage(FixedSlippage(0.001))
    # 设置交易成本
    set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.0002,
                             close_commission=0.0002, close_today_commission=0,
                             min_commission=5), type='fund')
    # 过滤日志级别
    log.set_level('system', 'error')

    # ===== ETF池 =====
    g.etf_pool = [
        '518880.XSHG',  # 黄金ETF（大宗商品）
        '513100.XSHG',  # 纳指100（海外资产）
        '159915.XSHE',  # 创业板100（成长股、科技股、中小盘）
        '510180.XSHG',  # 上证180（价值股、蓝筹股、中大盘）
    ]

    # ===== 策略参数 =====
    g.m_days = 25  # 动量参考天数

    log.info("=" * 60)
    log.info("【策略初始化】")
    log.info("-" * 60)
    log.info("    ETF池: %s" % ','.join(g.etf_pool))
    log.info("    动量天数: %d" % g.m_days)
    log.info("    持仓数量: 1只（动量最高）")
    log.info("    安全区: score > 0 且 <= 5")
    log.info("=" * 60)

    # 每日调仓
    run_daily(trade, '9:30')


# ============ 交易函数 ============
def trade(context):
    """执行每日调仓"""
    current_date = context.current_dt.strftime('%Y-%m-%d')

    log.info("=" * 60)
    log.info("【每日调仓】日期: %s | 时间: 09:30" % current_date)
    log.info("=" * 60)

    # ========== 1. 动量计算与选股 ==========
    rank_list = get_rank(g.etf_pool)
    target_num = 1
    target_info = rank_list[:target_num] if rank_list else []
    target_etf = target_info[0]['etf'] if target_info else None

    if target_etf:
        log.info(">>> 目标ETF: [%s] 得分=%.4f"
                 % (target_etf, target_info[0]['score']))
    else:
        log.info(">>> 目标ETF: 无（空仓观望）")

    # ========== 2. 资金状况 ==========
    total_value = context.portfolio.total_value
    cash = context.portfolio.available_cash
    positions_value = total_value - cash

    log.info("-" * 60)
    log.info(">>> 资金状况")
    log.info("    总资产: %.2f元" % total_value)
    log.info("    现金: %.2f元" % cash)
    log.info("    持仓市值: %.2f元" % positions_value)

    # ========== 3. 当前持仓 ==========
    hold_list = list(context.portfolio.positions)
    log.info("-" * 60)
    log.info(">>> 当前持仓: %d只" % len(hold_list))
    for etf in hold_list:
        pos = context.portfolio.positions[etf]
        log.info("    [%s] %d股 | 市值=%.2f元"
                 % (etf, pos.total_amount, pos.total_amount * pos.price))

    if not hold_list:
        log.info("    (空仓)")

    # ========== 4. 卖出阶段 ==========
    log.info("-" * 60)
    log.info(">>> 卖出阶段")
    sell_count = 0

    for etf in hold_list:
        if etf != target_etf:
            # 不在目标池，卖出
            pos = context.portfolio.positions[etf]
            sell_value = pos.total_amount * pos.price
            order_target_value(etf, 0)
            sell_count += 1
            log.info("    [%s] 卖出 → 清仓%d股，市值%.2f元"
                     % (etf, pos.total_amount, sell_value))
        else:
            log.info("    [%s] 继续持有（与目标一致）" % etf)

    if sell_count == 0:
        log.info("    无需卖出（持仓与目标一致）")

    # ========== 5. 买入阶段 ==========
    log.info("-" * 60)
    log.info(">>> 买入阶段")

    hold_list_after_sell = list(context.portfolio.positions)

    if target_etf and target_etf not in hold_list_after_sell:
        # 目标ETF不在持仓中，买入
        buy_value = context.portfolio.available_cash
        log.info("    [%s] 目标买入=%.2f元（满仓）" % (target_etf, buy_value))

        order_target_value(target_etf, buy_value)
        log.info("    [%s] 买入完成 → 下单%.2f元" % (target_etf, buy_value))
    elif target_etf:
        log.info("    [%s] 已持有，无需买入" % target_etf)
    else:
        log.info("    无目标ETF，空仓观望")

    log.info("=" * 60)


# ============ 盘后处理 ============
def after_trading_end(context):
    """盘后汇总"""
    current_date = context.current_dt.strftime('%Y-%m-%d')

    total_value = context.portfolio.total_value
    cash = context.portfolio.available_cash
    positions_value = total_value - cash

    hold_list = list(context.portfolio.positions)

    log.info("=" * 60)
    log.info("【盘后汇总】日期: %s" % current_date)
    log.info("-" * 60)
    log.info(">>> 资金状况")
    log.info("    总资产: %.2f元" % total_value)
    log.info("    现金: %.2f元" % cash)
    log.info("    持仓市值: %.2f元" % positions_value)

    log.info("-" * 60)
    log.info(">>> 持仓状态: %d只" % len(hold_list))
    for etf in hold_list:
        pos = context.portfolio.positions[etf]
        log.info("    [%s] %d股 | 市值=%.2f元 | 价格=%.3f"
                 % (etf, pos.total_amount, pos.total_amount * pos.price, pos.price))

    if not hold_list:
        log.info("    (空仓)")

    log.info("=" * 60)