# -*- coding: utf-8 -*-
"""
【五福闹新春】PTrade移植版 v1.0
原策略：聚宽文章 https://www.joinquant.com/post/69750
作者：烟花三月ETF
移植说明：
    - run_daily → handle_data 时间分发 + before_trading_start 盘前准备
    - every_bar → handle_data 每分钟检查
    - get_price → get_history（仅在 before_trading_start 中调用）
    - .XSHG/.XSHE → .SS/.SZ 代码格式
    - get_all_securities → 静态扩展池替代
    - get_extras → 溢价率过滤禁用
    - 新增前复权因子(fq_factor)、大单拆分(900000股)
"""

import numpy as np
import math
from datetime import datetime, date, timedelta


def initialize(context):
    if not is_trade():
        set_limit_mode('UNLIMITED')
        set_commission(commission_ratio=0.0001, min_commission=5.0)
        set_slippage(slippage=0.0001)

    set_benchmark('000300.XSHG')

    # ==================== 固定池（.XSHG→.SS, .XSHE→.SZ）====================
    g.fixed_etf_pool = [
        # 大宗商品ETF
        '518880.SS',   # 黄金ETF
        '161226.SZ',   # 国投白银LOF
        '159980.SZ',   # 有色ETF大成
        '501018.SS',   # 南方原油LOF
        '159985.SZ',   # 豆粕ETF
        # 海外ETF
        '513100.SS',   # 纳指ETF
        '159509.SZ',   # 纳指科技ETF景顺
        '513290.SS',   # 纳指生物
        '513500.SS',   # 标普500
        '159518.SZ',   # 标普油气ETF嘉实
        '159502.SZ',   # 标普生物科技ETF嘉实
        '159529.SZ',   # 标普消费ETF
        '513400.SS',   # 道琼斯
        '520830.SS',   # 沙特ETF
        '513520.SS',   # 日经ETF
        '513030.SS',   # 德国ETF
        # 港股ETF
        '513090.SS',   # 香港证券
        '513180.SS',   # 恒指科技
        '513120.SS',   # HK创新药
        '513330.SS',   # 恒生互联
        '513750.SS',   # 港股非银
        '159892.SZ',   # 恒生医药ETF
        '159605.SZ',   # 中概互联ETF
        '513190.SS',   # H股金融
        '510900.SS',   # 恒生中国
        '513630.SS',   # 香港红利
        '513920.SS',   # 港股通央企红利
        '159323.SZ',   # 港股通汽车ETF
        '513970.SS',   # 恒生消费
        # 指数ETF
        '510500.SS',   # 中证500ETF
        '512100.SS',   # 中证1000ETF
        '563300.SS',   # 中证2000
        '510300.SS',   # 沪深300ETF
        '512050.SS',   # A500ETF
        '510760.SS',   # 上证ETF
        '159915.SZ',   # 创业板ETF易方达
        '159949.SZ',   # 创业板50ETF
        '159967.SZ',   # 创业板成长ETF
        '588080.SS',   # 科创板50
        '588220.SS',   # 科创100
        '511380.SS',   # 可转债ETF
        # 行业ETF
        '513310.SS',   # 中韩芯片
        '588200.SS',   # 科创芯片
        '159852.SZ',   # 软件ETF
        '512880.SS',   # 证券ETF
        '159206.SZ',   # 卫星ETF
        '512400.SS',   # 有色金属ETF
        '512980.SS',   # 传媒ETF
        '159516.SZ',   # 半导体设备ETF
        '512480.SS',   # 半导体
        '515880.SS',   # 通信ETF
        '562500.SS',   # 机器人
        '159218.SZ',   # 卫星产业ETF
        '159869.SZ',   # 游戏ETF
        '159870.SZ',   # 化工ETF
        '159326.SZ',   # 电网设备ETF
        '159851.SZ',   # 金融科技ETF
        '560860.SS',   # 工业有色
        '159363.SZ',   # 创业板人工智能ETF
        '588170.SS',   # 科创半导
        '159755.SZ',   # 电池ETF
        '512170.SS',   # 医疗ETF
        '512800.SS',   # 银行ETF
        '159819.SZ',   # 人工智能ETF易方达
        '512710.SS',   # 军工龙头
        '159638.SZ',   # 高端装备ETF
        '517520.SS',   # 黄金股
        '515980.SS',   # 人工智能
        '159995.SZ',   # 芯片ETF
        '159227.SZ',   # 航空航天ETF
        '512660.SS',   # 军工ETF
        '512690.SS',   # 酒ETF
        '516150.SS',   # 稀土基金
        '512890.SS',   # 红利低波
        '588790.SS',   # 科创智能
        '159992.SZ',   # 创新药ETF
        '512070.SS',   # 证券保险
        '562800.SS',   # 稀有金属
        '512010.SS',   # 医药ETF
        '515790.SS',   # 光伏ETF
        '510880.SS',   # 红利ETF
        '159928.SZ',   # 消费ETF
        '159883.SZ',   # 医疗器械ETF
        '159998.SZ',   # 计算机ETF
        '515220.SS',   # 煤炭ETF
        '561980.SS',   # 芯片设备
        '515400.SS',   # 大数据
        '515120.SS',   # 创新药广发
        '159566.SZ',   # 储能电池ETF
        '515050.SS',   # 5GETF
        '516510.SS',   # 云计算ETF
        '159256.SZ',   # 创业板软件ETF
        '159766.SZ',   # 旅游ETF
        '512200.SS',   # 地产ETF
        '513350.SS',   # 油气ETF
        '159583.SZ',   # 通信设备ETF
        '159732.SZ',   # 消费电子ETF
        '516160.SS',   # 新能源
        '516520.SS',   # 智能驾驶
        '562590.SS',   # 半导材料
        '515030.SS',   # 新汽车
        '512670.SS',   # 国防ETF
        '561330.SS',   # 矿业ETF
        '516190.SS',   # 文娱ETF
        '159840.SZ',   # 锂电池ETF
        '159611.SZ',   # 电力ETF
        '159981.SZ',   # 能源化工ETF
        '159865.SZ',   # 养殖ETF
        '561360.SS',   # 石油ETF
        '159667.SZ',   # 工业母机ETF
        '515170.SS',   # 食品饮料ETF
        '513360.SS',   # 教育ETF
        '159825.SZ',   # 农业ETF
        '515210.SS',   # 钢铁ETF
    ]

    # ==================== 扩展池（替代动态池全市场扫描）====================
    g.extended_etf_pool = [
        # 宽基补充
        '510050.SS',   # 上证50ETF
        '510180.SS',   # 上证180ETF
        '510800.SS',   # 中证800ETF
        '512500.SS',   # 中证500ETF南方
        '159919.SZ',   # 沪深300ETF嘉实
        '588000.SS',   # 科创50ETF华夏
        '588330.SS',   # 科创200ETF
        '159901.SZ',   # 深证100ETF
        '159922.SZ',   # 中证500ETF嘉实
        '510330.SS',   # 沪深300ETF华夏
        # 行业主题补充
        '515000.SS',   # 科技ETF
        '515180.SS',   # 红利ETF易方达
        '515260.SS',   # 新能源车ETF
        '515300.SS',   # 大金融ETF
        '515330.SS',   # 互联网ETF
        '515700.SS',   # 新能车ETF
        '515750.SS',   # 信创ETF
        '515800.SS',   # 环保ETF
        '515850.SS',   # 证券龙头ETF
        '515900.SS',   # 央企创新ETF
        '512020.SS',   # 万家经济新动能
        '512030.SS',   # 新能源车LOF
        '512040.SS',   # 转型ETF
        '512120.SS',   # 医药50ETF
        '512130.SS',   # 工程机械ETF
        '512150.SS',   # 创50ETF
        '512160.SS',   # MSCI基金
        '512180.SS',   # 建信MSCI
        '512220.SS',   # 景顺MSCI
        '512290.SS',   # 生物医药ETF
        '512300.SS',   # 医药卫生ETF
        '512310.SS',   # 证券公司ETF
        '512330.SS',   # 消费龙头ETF
        '512340.SS',   # 中证500低波
        '512380.SS',   # MSCI质量
        '512510.SS',   # 中证500ETF广发
        '512520.SS',   # MSCI国际通
        '512560.SS',   # 中国国企ETF
        '512580.SS',   # 中证环保ETF
        '512600.SS',   # 主要消费ETF
        '512640.SS',   # 金融地产ETF
        '512700.SS',   # 银行ETF天弘
        '512760.SS',   # 芯片龙头ETF
        '512770.SS',   # 中证银行ETF
        '512810.SS',   # 军工龙头ETF
        '512900.SS',   # 证券ETF基金
        '512910.SS',   # 中证100ETF
        '512950.SS',   # 央企结构调整ETF
        '512960.SS',   # 央企创新ETF博时
        '513010.SS',   # 恒生ETF
        '513050.SS',   # 中概互联网ETF
        '513060.SS',   # 恒生医疗ETF
        '513080.SS',   # 法国CAC40ETF
        '513110.SS',   # 恒生科技30ETF
        '513130.SS',   # 恒生科技ETF华安
        '513150.SS',   # 中概互联网LOF
        '513160.SS',   # 亚太精选ETF
        '513200.SS',   # 日经225ETF
        '513300.SS',   # 纳指100ETF
        '513320.SS',   # 亚洲龙头ETF
        '513380.SS',   # 恒生红利低波ETF
        '513550.SS',   # 港股通50ETF
        '513560.SS',   # 恒生A股龙头ETF
        '513600.SS',   # 恒生科技指数ETF
        '513650.SS',   # 港股通高股息ETF
        '513660.SS',   # 恒生科技30ETF华泰
        '513680.SS',   # 港股通科技30ETF
        '513700.SS',   # 日经225ETF易方达
        '513730.SS',   # 东南亚科技ETF
        '513800.SS',   # 恒生科技ETF华夏
        '513850.SS',   # 港股通红利ETF
        '513860.SS',   # 恒生红利ETF
        '516510.SS',   # 云计算ETF
        '516560.SS',   # 新材料ETF
        '516580.SS',   # 央企改革ETF
        '516600.SS',   # 基建50ETF
        '516630.SS',   # 碳中和ETF
        '516670.SS',   # 畜牧养殖ETF
        '516700.SS',   # 物联网ETF
        '516770.SS',   # 智能电动车ETF
        '516800.SS',   # 智能制造ETF
        '516850.SS',   # 央企科技ETF
        '516950.SS',   # 基建ETF
        '516970.SS',   # 基建工程ETF
        '517180.SS',   # 有色50ETF
        '159611.SZ',   # 电力ETF广发
        '159745.SZ',   # 国防军工ETF
        '159755.SZ',   # 电池ETF广发
        '159786.SZ',   # 半导体ETF
        '159801.SZ',   # 碳中和50ETF
        '159805.SZ',   # 新能源ETF
        '159806.SZ',   # 新能源车ETF
        '159812.SZ',   # 养殖ETF
        '159813.SZ',   # 光伏产业ETF
        '159820.SZ',   # 芯片ETF
        '159841.SZ',   # 东财创业板ETF
        '159845.SZ',   # 中证红利ETF
        '159855.SZ',   # 中证1000ETF
        '159857.SZ',   # 光伏30ETF
        '159861.SZ',   # 中证500ETF
        '159875.SZ',   # 新能源80ETF
        '159880.SZ',   # 科创板ETF
        '159890.SZ',   # 有色金属ETF
        '159901.SZ',   # 深证100ETF
        '159905.SZ',   # 深证红利ETF
        '159920.SZ',   # 恒生ETF
        '159941.SZ',   # 纳指ETF
        '159952.SZ',   # 创业板ETF
        '159966.SZ',   # 创业板ETF博时
        '159996.SZ',   # 家电ETF
    ]

    # ==================== 策略核心参数 ====================
    g.holdings_num = 1
    g.defensive_etf = '511880.SS'
    g.min_money = 10
    g.max_order_shares = 900000

    # 动量计算参数
    g.lookback_days = 25
    g.min_score_threshold = 0
    g.max_score_threshold = 5
    g.score_threshold_ratio = 0.9

    # 短期动量参数
    g.use_short_momentum_period = False
    g.short_momentum_lookback = 21
    g.short_momentum_min_score = 0
    g.short_momentum_max_score = 6

    # 过滤开关及参数
    g.enable_r2_filter = True
    g.r2_threshold = 0.4
    g.enable_volume_check = True
    g.volume_lookback = 5
    g.volume_threshold = 1.8
    g.enable_loss_filter = True
    g.loss = 0.97
    g.enable_premium_filter = False
    g.max_premium_rate = 30

    # 滤波器参数
    g.laplace_s_param = 0.05
    g.laplace_min_slope = 0.002
    g.gaussian_sigma = 1.2
    g.gaussian_min_slope = 0.002

    # ==================== 震荡期参数 ====================
    g.enable_range_bound_mode = True
    g.current_filter = '正常期'
    g.risk_state = '正常期'
    g.lookback_high_low_days = 20
    g.risk_benchmark = '510300.SS'

    g.enable_bias_trigger = True
    g.bias_threshold = 0.08
    g.ma_period = 20
    g.enable_rsi_trigger = True
    g.rsi_overbought = 70
    g.rsi_pullback = 65
    g.previous_rsi = None
    g.enable_stop_loss_trigger = True
    g.stop_loss_triggered_today = False

    g.enable_low_point_rise_trigger = True
    g.low_point_rise_threshold = 0.04
    g.enable_stable_signal_trigger = True
    g.drawdown_recovery = 0.02
    g.max_range_bound_days = 20
    g.stable_days = 0

    g.filter_switch_cooldown = 3
    g.last_switch_date = None
    g.range_bound_start_date = None
    g.range_bound_days_count = 0

    # 风险监控
    g.previous_drawdown = None
    g.max_portfolio_value = 0
    g.drawdown_threshold = 0.03

    # 止损参数
    g.use_fixed_stop_loss = True
    g.fixedStopLossThreshold = 0.95
    g.use_pct_stop_loss = False
    g.pct_stop_loss_threshold = 0.95

    # ==================== 运行时缓存 ====================
    g.filtered_fixed_pool = []
    g.dynamic_etf_pool = []
    g.merged_etf_pool = []
    g.ranked_etfs_result = []
    g.target_etfs_list = []
    g.fq_factor = {}
    g.yesterday_close_cache = {}
    g.pool_close_history = {}
    g.pool_volume_history = {}
    g.pool_today_volume = {}
    g.benchmark_close_history = None
    g.benchmark_high_history = None
    g.benchmark_low_history = None
    g.avg_etf_money_threshold = None
    g.afternoon_done = False
    g.stop_loss_checked_minute = None
    g.first_run = True

    set_universe(g.fixed_etf_pool)

    log.info("=" * 60)
    log.info("【五福闹新春】PTrade移植版 v1.0 启动")
    log.info("  持仓: %d只, 动量周期: %d天, 防御: %s" % (
        g.holdings_num, g.lookback_days, g.defensive_etf))
    log.info("  止损: 成本×%.0f%%, 震荡期: %s" % (
        g.fixedStopLossThreshold * 100,
        '启用' if g.enable_range_bound_mode else '禁用'))
    log.info("=" * 60)


# ==================== 盘前准备 ====================
def before_trading_start(context, data):
    g.afternoon_done = False
    g.stop_loss_checked_minute = None
    g.stop_loss_triggered_today = False

    _morning_routine(context)

    if g.first_run:
        g.first_run = False
        _init_range_bound_status()

    log.info("[盘前] 准备完成, 合并池: %d只" % len(g.merged_etf_pool))


def _morning_routine(context):
    log.info("=" * 60)
    log.info("[晨间流水线] 启动...")
    _check_positions()
    _monitor_drawdown(context)
    _calculate_liquidity_threshold()
    _filter_fixed_pool()
    _filter_extended_pool()
    _merge_pools()
    _cache_pool_history()
    _cache_benchmark_history()
    _cache_yesterday_close()
    _cache_fq_factors()
    log.info("[晨间流水线] 完成")


def _check_positions():
    positions = get_positions()
    if not positions:
        log.info("[持仓检查] 当前空仓")
        return
    for sec in positions.keys():
        pos = positions[sec]
        if pos.total_amount > 0:
            log.info("[持仓] %s 数量:%d 成本:%.3f" % (sec, pos.total_amount, pos.cost_basis))


def _monitor_drawdown(context):
    try:
        current_value = context.portfolio.total_value
        if current_value > g.max_portfolio_value:
            g.max_portfolio_value = current_value
        if g.max_portfolio_value > 0:
            dd = (g.max_portfolio_value - current_value) / g.max_portfolio_value
            if dd >= g.drawdown_threshold:
                log.info("[回撤预警] %.2f%% (阈值%.0f%%)" % (dd * 100, g.drawdown_threshold * 100))
    except:
        pass


def _calculate_liquidity_threshold():
    try:
        all_pool = g.fixed_etf_pool + g.extended_etf_pool
        his = get_history(3, frequency='1d', field='money',
                          security_list=all_pool, fq=None,
                          include=False, is_dict=True)
        if not his:
            g.avg_etf_money_threshold = 10000000
            return

        total_money = 0.0
        count = 0
        for sec in his.keys():
            if his[sec] and 'money' in his[sec]:
                money_list = his[sec]['money']
                if money_list:
                    total_money += sum(money_list)
                    count += len(money_list)

        if count > 0:
            avg_daily_total = total_money / 3.0
            threshold = avg_daily_total / 20000.0
            g.avg_etf_money_threshold = max(threshold, 10000000)
        else:
            g.avg_etf_money_threshold = 10000000

        log.info("[流动性阈值] %.0f万元" % (g.avg_etf_money_threshold / 10000))
    except:
        g.avg_etf_money_threshold = 10000000


def _filter_fixed_pool():
    threshold = g.avg_etf_money_threshold
    if threshold is None:
        threshold = 10000000
    try:
        his = get_history(3, frequency='1d', field='money',
                          security_list=g.fixed_etf_pool, fq=None,
                          include=False, is_dict=True)
        filtered = []
        for sec in g.fixed_etf_pool:
            try:
                if his and sec in his and his[sec] and 'money' in his[sec]:
                    money_list = his[sec]['money']
                    if money_list and len(money_list) >= 2:
                        avg_money = sum(money_list) / len(money_list)
                        if avg_money >= threshold:
                            filtered.append(sec)
                    else:
                        filtered.append(sec)
                else:
                    filtered.append(sec)
            except:
                filtered.append(sec)
        g.filtered_fixed_pool = filtered
        log.info("[固定池过滤] %d只 -> %d只" % (len(g.fixed_etf_pool), len(filtered)))
    except:
        g.filtered_fixed_pool = g.fixed_etf_pool[:]


def _filter_extended_pool():
    threshold = g.avg_etf_money_threshold
    if threshold is None:
        threshold = 10000000
    extended_new = [s for s in g.extended_etf_pool if s not in g.fixed_etf_pool]
    if not extended_new:
        g.dynamic_etf_pool = []
        return
    try:
        his = get_history(3, frequency='1d', field='money',
                          security_list=extended_new, fq=None,
                          include=False, is_dict=True)
        filtered = []
        for sec in extended_new:
            try:
                if his and sec in his and his[sec] and 'money' in his[sec]:
                    money_list = his[sec]['money']
                    if money_list and len(money_list) >= 2:
                        avg_money = sum(money_list) / len(money_list)
                        if avg_money >= threshold:
                            filtered.append(sec)
            except:
                pass
        g.dynamic_etf_pool = filtered
        log.info("[扩展池过滤] %d只 -> %d只" % (len(extended_new), len(filtered)))
    except:
        g.dynamic_etf_pool = []


def _merge_pools():
    merged = list(set(g.filtered_fixed_pool + g.dynamic_etf_pool))
    merged.sort()
    g.merged_etf_pool = merged
    log.info("[合并池] 固定%d + 扩展%d = %d只" % (
        len(g.filtered_fixed_pool), len(g.dynamic_etf_pool), len(merged)))
    set_universe(merged)


def _cache_pool_history():
    if not g.merged_etf_pool:
        g.pool_close_history = {}
        g.pool_volume_history = {}
        return
    lookback = max(g.lookback_days, g.short_momentum_lookback, g.volume_lookback) + 20
    try:
        his_close = get_history(lookback, frequency='1d', field='close',
                                security_list=g.merged_etf_pool, fq='pre',
                                include=False, is_dict=True)
        his_vol = get_history(lookback, frequency='1d', field='volume',
                              security_list=g.merged_etf_pool, fq=None,
                              include=False, is_dict=True)
        g.pool_close_history = his_close if his_close else {}
        g.pool_volume_history = his_vol if his_vol else {}
    except:
        g.pool_close_history = {}
        g.pool_volume_history = {}


def _cache_benchmark_history():
    if not g.enable_range_bound_mode:
        return
    try:
        lookback = max(g.ma_period, g.lookback_high_low_days) + 30
        his_close = get_history(lookback, frequency='1d', field='close',
                                security_list=g.risk_benchmark, fq=None,
                                include=False, is_dict=True)
        his_high = get_history(lookback, frequency='1d', field='high',
                               security_list=g.risk_benchmark, fq=None,
                               include=False, is_dict=True)
        his_low = get_history(lookback, frequency='1d', field='low',
                              security_list=g.risk_benchmark, fq=None,
                              include=False, is_dict=True)
        g.benchmark_close_history = his_close[g.risk_benchmark]['close'] if (his_close and g.risk_benchmark in his_close and his_close[g.risk_benchmark] and 'close' in his_close[g.risk_benchmark]) else None
        g.benchmark_high_history = his_high[g.risk_benchmark]['high'] if (his_high and g.risk_benchmark in his_high and his_high[g.risk_benchmark] and 'high' in his_high[g.risk_benchmark]) else None
        g.benchmark_low_history = his_low[g.risk_benchmark]['low'] if (his_low and g.risk_benchmark in his_low and his_low[g.risk_benchmark] and 'low' in his_low[g.risk_benchmark]) else None
    except:
        g.benchmark_close_history = None
        g.benchmark_high_history = None
        g.benchmark_low_history = None


def _cache_yesterday_close():
    positions = get_positions()
    g.yesterday_close_cache = {}
    if not positions:
        return
    for sec in positions.keys():
        try:
            his = get_history(1, frequency='1d', field='close',
                              security_list=sec, fq=None,
                              include=False, is_dict=True)
            if his and sec in his and his[sec] and 'close' in his[sec]:
                closes = his[sec]['close']
                if closes:
                    g.yesterday_close_cache[sec] = closes[-1]
        except:
            pass


def _cache_fq_factors():
    g.fq_factor = {}
    all_secs = list(set(g.merged_etf_pool + list(get_positions().keys())))
    if not all_secs:
        return
    try:
        his_fq = get_history(1, frequency='1d', field='close',
                             security_list=all_secs, fq='pre',
                             include=False, is_dict=True)
        his_raw = get_history(1, frequency='1d', field='close',
                              security_list=all_secs, fq=None,
                              include=False, is_dict=True)
        if his_fq and his_raw:
            for sec in all_secs:
                try:
                    fq_c = his_fq.get(sec, {}).get('close', [])
                    raw_c = his_raw.get(sec, {}).get('close', [])
                    if fq_c and raw_c and raw_c[-1] > 0:
                        g.fq_factor[sec] = fq_c[-1] / raw_c[-1]
                    else:
                        g.fq_factor[sec] = 1.0
                except:
                    g.fq_factor[sec] = 1.0
    except:
        for sec in all_secs:
            g.fq_factor[sec] = 1.0


def _init_range_bound_status():
    if not g.enable_range_bound_mode:
        return
    if g.benchmark_close_history is None:
        return
    close = np.array(g.benchmark_close_history)
    if len(close) < max(g.ma_period, g.lookback_high_low_days):
        return

    current_price = close[-1]
    ma = np.mean(close[-g.ma_period:])
    bias = (current_price - ma) / ma if ma > 0 else 0

    should_enter = False
    signals = []

    if g.enable_bias_trigger and bias > g.bias_threshold:
        should_enter = True
        signals.append("乖离率%.2f%%>%.0f%%" % (bias * 100, g.bias_threshold * 100))

    if g.enable_rsi_trigger:
        current_rsi = _calculate_rsi(close, 14)
        if current_rsi is not None and len(close) >= 15:
            prev_rsi = _calculate_rsi(close[:-1], 14)
            if prev_rsi is not None and prev_rsi > g.rsi_overbought and current_rsi < g.rsi_pullback:
                should_enter = True
                signals.append("RSI超买回落%.1f->%.1f" % (prev_rsi, current_rsi))

    if should_enter:
        g.current_filter = '震荡期'
        g.risk_state = '震荡期'
        g.range_bound_start_date = date.today()
        g.range_bound_days_count = 0
        log.info("[首次运行] 进入震荡期: %s" % '; '.join(signals))
    else:
        g.current_filter = '正常期'
        g.risk_state = '正常期'
        if g.benchmark_high_history is not None:
            high = np.array(g.benchmark_high_history)
            recent_high = np.max(high[-g.lookback_high_low_days:])
            g.previous_drawdown = (recent_high - current_price) / recent_high if recent_high > 0 else 0
        g.previous_rsi = _calculate_rsi(close, 14)
        log.info("[首次运行] 正常期, 乖离率: %.2f%%" % (bias * 100))


# ==================== 盘中主函数 ====================
def handle_data(context, data):
    dt = context.blotter.current_dt
    current_time = dt.strftime('%H:%M')

    if current_time == '13:10':
        _afternoon_routine(context, data)

    if ('09:31' <= current_time <= '11:30') or ('13:00' <= current_time <= '14:57'):
        _minute_level_stop_loss(context, data)
        _minute_level_pct_stop_loss(context, data)


# ==================== 盘后函数 ====================
def after_trading_end(context, data):
    g.cache_date = None
    g.yesterday_close_cache = {}
    if g.current_filter == '震荡期' and g.range_bound_start_date is not None:
        g.range_bound_days_count += 1
        log.info("震荡期已持续 %d 个交易日" % g.range_bound_days_count)
    log.info("收盘缓存重置完成")


# ==================== 午后交易流水线 ====================
def _afternoon_routine(context, data):
    log.info("=" * 60)
    log.info("[午后交易流水线] 启动...")
    log.info("[震荡期退出检查]")
    _check_and_exit_range_bound(context)
    log.info("[震荡期进入检查]")
    _check_and_enter_range_bound(context, data)
    log.info("[动量计算] 计算动量得分与排序...")
    final_list = _get_final_ranked_etfs(context, data)
    log.info("[卖出执行]")
    _execute_sell_trades(context, data, final_list)
    log.info("[买入执行]")
    _execute_buy_trades(context, data, final_list)
    log.info("[午后交易流水线] 执行完毕")


# ==================== 震荡期退出检查 ====================
def _check_and_exit_range_bound(context):
    if not g.enable_range_bound_mode:
        return
    if g.current_filter != '震荡期':
        return
    log.info("[震荡期退出检查] 开始检测退出条件...")

    if g.benchmark_close_history is None:
        log.info("[震荡期退出检查] 基准数据不足，跳过")
        return

    close = np.array(g.benchmark_close_history)
    high = np.array(g.benchmark_high_history) if g.benchmark_high_history else close
    low = np.array(g.benchmark_low_history) if g.benchmark_low_history else close

    if len(close) < max(g.ma_period, g.lookback_high_low_days):
        log.info("[震荡期退出检查] 数据不足，跳过")
        return

    current_price = close[-1]
    n = g.lookback_high_low_days
    recent_high = np.max(high[-n:])
    recent_low = np.min(low[-n:])
    current_drawdown = (recent_high - current_price) / recent_high if recent_high > 0 else 0
    rise_from_low = (current_price - recent_low) / recent_low if recent_low > 0 else 0

    recovery_signals = []
    ma = np.mean(close[-g.ma_period:])
    current_rsi = _calculate_rsi(close, 14)

    log.info("[震荡期数据] 当前价: %.3f, 近%d日高点: %.3f, 低点: %.3f" % (
        current_price, n, recent_high, recent_low))
    log.info("[震荡期数据] 回撤: %.2f%%, 从低点涨幅: %.2f%%" % (
        current_drawdown * 100, rise_from_low * 100))

    if g.enable_low_point_rise_trigger:
        if rise_from_low >= g.low_point_rise_threshold:
            recovery_signals.append("从近%d日低点上涨%.2f%%>=%.0f%%" % (
                n, rise_from_low * 100, g.low_point_rise_threshold * 100))

    if g.enable_stable_signal_trigger:
        if current_price > ma:
            recovery_signals.append("价格站上均线")
        if len(close) >= 2 and close[-1] > close[-2]:
            recovery_signals.append("价格回升")
        if g.previous_drawdown is not None and current_drawdown < g.previous_drawdown:
            recovery_signals.append("回撤收窄(%.2f%%<%.2f%%)" % (
                current_drawdown * 100, g.previous_drawdown * 100))
        if current_rsi is not None and g.previous_rsi is not None and current_rsi > g.previous_rsi:
            recovery_signals.append("RSI回升(%.1f)" % current_rsi)
        drawdown_safe = current_drawdown < g.drawdown_recovery
        if drawdown_safe:
            g.stable_days += 1
        else:
            g.stable_days = 0

    g.previous_drawdown = current_drawdown
    g.previous_rsi = current_rsi

    range_bound_days = g.range_bound_days_count
    if range_bound_days >= g.max_range_bound_days:
        recovery_signals.append("震荡期满(%d个交易日)" % range_bound_days)

    low_point_rise_condition = (g.enable_low_point_rise_trigger and
                                rise_from_low >= g.low_point_rise_threshold)
    stable_signal_condition = False
    if g.enable_stable_signal_trigger:
        drawdown_safe = current_drawdown < g.drawdown_recovery
        stable_signal_condition = (drawdown_safe and
                                   len(recovery_signals) >= 2 and
                                   g.stable_days >= 2)
    force_condition = range_bound_days >= g.max_range_bound_days
    should_recover = low_point_rise_condition or stable_signal_condition or force_condition

    if should_recover:
        can_switch = True
        if g.last_switch_date is not None:
            days_since = (date.today() - g.last_switch_date).days
            if days_since < g.filter_switch_cooldown:
                can_switch = False
                log.info("[震荡期退出] 冷却期中，距上次切换 %d 天" % days_since)
        if can_switch:
            g.current_filter = '正常期'
            g.risk_state = '正常期'
            g.last_switch_date = date.today()
            g.range_bound_start_date = None
            g.range_bound_days_count = 0
            g.stable_days = 0
            log.info("[退出震荡期] 切换回拉普拉斯滤波器: %s" % '; '.join(recovery_signals))
        else:
            log.info("[震荡期退出] 冷却期内，暂不切换")
    else:
        log.info("[震荡期退出检查] 未满足退出条件，保持震荡期(高斯滤波器)")


# ==================== 震荡期进入检查 ====================
def _check_and_enter_range_bound(context, data):
    if not g.enable_range_bound_mode:
        return
    if g.current_filter == '震荡期':
        log.info("[震荡期检查] 当前已在震荡期，滤波器: 高斯")
        return

    can_switch = True
    if g.last_switch_date is not None:
        days_since = (date.today() - g.last_switch_date).days
        if days_since < g.filter_switch_cooldown:
            can_switch = False
            log.info("[震荡期检查] 冷却期中，距上次切换 %d 天 (需%d天)" % (
                days_since, g.filter_switch_cooldown))
    if not can_switch:
        return

    risk_signals = []

    if g.benchmark_close_history is not None:
        close = np.array(g.benchmark_close_history)
        if len(close) >= max(g.ma_period, g.lookback_high_low_days):
            current_price = close[-1]
            if g.enable_bias_trigger:
                ma = np.mean(close[-g.ma_period:])
                bias = (current_price - ma) / ma if ma > 0 else 0
                if bias > g.bias_threshold:
                    risk_signals.append("乖离率过大(%.2f%%>%.0f%%)" % (
                        bias * 100, g.bias_threshold * 100))
            if g.enable_rsi_trigger:
                current_rsi = _calculate_rsi(close, 14)
                if len(close) >= 15 and current_rsi is not None:
                    prev_rsi = _calculate_rsi(close[:-1], 14)
                    if (prev_rsi is not None and
                            prev_rsi > g.rsi_overbought and
                            current_rsi < g.rsi_pullback and
                            current_rsi < prev_rsi):
                        risk_signals.append("RSI超买回落(%.1f->%.1f)" % (prev_rsi, current_rsi))

    if g.enable_stop_loss_trigger and g.stop_loss_triggered_today:
        risk_signals.append("今日触发止损")
        g.stop_loss_triggered_today = False

    if len(risk_signals) > 0:
        g.current_filter = '震荡期'
        g.risk_state = '震荡期'
        g.last_switch_date = date.today()
        g.range_bound_start_date = date.today()
        g.range_bound_days_count = 0
        g.stable_days = 0
        log.info("[进入震荡期] 切换到高斯滤波器: %s" % '; '.join(risk_signals))
    else:
        log.info("[震荡期检查] 未满足进入条件，保持正常期(拉普拉斯滤波器)")


# ==================== 动量得分计算 ====================
def _calculate_momentum_score(price_series, lookback_days):
    if len(price_series) < lookback_days + 1:
        return None, None, None
    recent = price_series[-(lookback_days + 1):]
    y = np.log(recent)
    x = np.arange(len(y))
    weights = np.linspace(1, 2, len(y))
    W = weights ** 2
    W_sum = np.sum(W)
    x_bar = np.sum(W * x) / W_sum
    y_bar = np.sum(W * y) / W_sum
    dx = x - x_bar
    dy = y - y_bar
    variance_x = np.sum(W * dx ** 2)
    if variance_x == 0:
        return 0, 0, 0
    slope = np.sum(W * dx * dy) / variance_x
    intercept = y_bar - slope * x_bar
    annualized_returns = math.exp(slope * 250) - 1
    y_pred = slope * x + intercept
    ss_res = np.sum(weights * (y - y_pred) ** 2)
    ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot else 0
    momentum_score = annualized_returns * r_squared
    return momentum_score, annualized_returns, r_squared


# ==================== 滤波器函数 ====================
def _laplace_filter(price, s=0.05):
    alpha = 1 - np.exp(-s)
    L = np.zeros(len(price))
    L[0] = price[0]
    for t in range(1, len(price)):
        L[t] = alpha * price[t] + (1 - alpha) * L[t - 1]
    return L


def _gaussian_filter_last_two(price, sigma=1.2):
    n = len(price)
    if n < 2:
        return 0, 0
    idx_1 = np.arange(n)
    weights_1 = np.exp(-((idx_1 + 1) ** 2) / (2 * sigma ** 2))[::-1]
    weights_1 /= np.sum(weights_1)
    g1 = np.sum(price * weights_1)
    price_2 = price[:-1]
    idx_2 = np.arange(n - 1)
    weights_2 = np.exp(-((idx_2 + 1) ** 2) / (2 * sigma ** 2))[::-1]
    weights_2 /= np.sum(weights_2)
    g2 = np.sum(price_2 * weights_2)
    return g1, g2


def _calculate_rsi(close, period=14):
    try:
        if len(close) < period + 1:
            return None
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    except:
        return None


# ==================== 成交量比计算 ====================
def _get_volume_ratio(hist_volumes, today_vol, context):
    try:
        lookback = g.volume_lookback
        if hist_volumes is None or len(hist_volumes) < lookback:
            return None
        past_n = hist_volumes[-lookback:]
        if np.any(np.isnan(past_n)) or np.any(past_n == 0):
            return None
        avg_volume = np.mean(past_n)
        if avg_volume == 0:
            return None
        dt = context.blotter.current_dt
        elapsed_minutes = (dt.hour - 9) * 60 + dt.minute - 30
        if dt.hour >= 13:
            elapsed_minutes -= 90
        elapsed_minutes = max(1, min(elapsed_minutes, 240))
        projected_today_vol = today_vol * (240.0 / elapsed_minutes)
        return projected_today_vol / avg_volume if avg_volume > 0 else 0
    except:
        return None


# ==================== 指标计算 ====================
def _calculate_all_metrics(etf, hist_closes, hist_volumes, current_price, today_vol, context):
    try:
        price_series = np.append(hist_closes, current_price)
        if len(price_series) < max(g.lookback_days, g.short_momentum_lookback) * 0.8:
            return None

        momentum_score, annualized_returns, r_squared = _calculate_momentum_score(
            price_series, g.lookback_days)
        if momentum_score is None:
            return None

        short_momentum_score, _, _ = _calculate_momentum_score(
            price_series, g.short_momentum_lookback)

        passed_momentum = (g.min_score_threshold <= momentum_score <= g.max_score_threshold)
        passed_short_momentum = False
        if short_momentum_score is not None:
            passed_short_momentum = (g.short_momentum_min_score <= short_momentum_score <= g.short_momentum_max_score)

        volume_ratio = _get_volume_ratio(hist_volumes, today_vol, context)

        passed_loss = True
        day_ratios = []
        if len(price_series) >= 4:
            day1 = price_series[-1] / price_series[-2]
            day2 = price_series[-2] / price_series[-3]
            day3 = price_series[-3] / price_series[-4]
            day_ratios = [day1, day2, day3]
            if min(day_ratios) < g.loss:
                passed_loss = False

        laplace_slope = 0.0
        passed_laplace = False
        gaussian_slope = 0.0
        passed_gaussian = False

        if len(price_series) >= 10:
            try:
                lv = _laplace_filter(price_series, s=g.laplace_s_param)
                if len(lv) >= 2:
                    laplace_slope = lv[-1] - lv[-2]
                    passed_laplace = (current_price > lv[-1] and laplace_slope > g.laplace_min_slope)
                gv1, gv2 = _gaussian_filter_last_two(price_series, sigma=g.gaussian_sigma)
                gaussian_slope = gv1 - gv2
                passed_gaussian = (current_price > gv1 and gaussian_slope > g.gaussian_min_slope)
            except:
                pass

        if g.current_filter == '正常期':
            passed_filter = passed_laplace
        else:
            passed_filter = passed_gaussian

        return {
            'etf': etf,
            'momentum_score': momentum_score,
            'short_momentum_score': short_momentum_score if short_momentum_score is not None else float('-inf'),
            'annualized_returns': annualized_returns,
            'r_squared': r_squared,
            'current_price': current_price,
            'volume_ratio': volume_ratio,
            'day_ratios': day_ratios,
            'passed_momentum': passed_momentum,
            'passed_short_momentum': passed_short_momentum,
            'passed_r2': r_squared > g.r2_threshold,
            'passed_volume': volume_ratio is not None and volume_ratio < g.volume_threshold,
            'passed_loss': passed_loss,
            'passed_premium': True,
            'laplace_slope': laplace_slope,
            'gaussian_slope': gaussian_slope,
            'passed_laplace': passed_laplace,
            'passed_gaussian': passed_gaussian,
            'passed_filter': passed_filter,
        }
    except:
        return None


# ==================== 过滤条件 ====================
def _apply_filters(metrics_list):
    use_short = g.use_short_momentum_period
    steps = [
        ('动量得分', lambda m: m['passed_momentum'], not use_short),
        ('短期动量', lambda m: m['passed_short_momentum'], use_short),
        ('R2', lambda m: m['passed_r2'], g.enable_r2_filter),
        ('成交量', lambda m: m['passed_volume'], g.enable_volume_check),
        ('短期风控', lambda m: m['passed_loss'], g.enable_loss_filter),
        ('溢价率', lambda m: m['passed_premium'], g.enable_premium_filter),
        ('动态滤波', lambda m: m['passed_filter'], g.enable_range_bound_mode),
    ]
    filtered = metrics_list[:]
    for name, condition, is_enabled in steps:
        if is_enabled:
            before = len(filtered)
            filtered = [m for m in filtered if condition(m)]
            after = len(filtered)
            if before > after:
                log.info("[过滤] %s: %d/%d 通过" % (name, after, before))
    return filtered


# ==================== 主筛选函数 ====================
def _get_final_ranked_etfs(context, data):
    if not hasattr(g, 'merged_etf_pool') or not g.merged_etf_pool:
        log.info("[动量计算] 合并池为空")
        return []

    etf_set = list(g.merged_etf_pool)
    log.info("[动量得分计算] 合并池共%d只ETF" % len(etf_set))
    log.info("[当前滤波器] %s" % ('拉普拉斯(正常期)' if g.current_filter == '正常期' else '高斯(震荡期)'))

    use_short = g.use_short_momentum_period
    score_key = 'short_momentum_score' if use_short else 'momentum_score'
    lookback = max(g.lookback_days, g.short_momentum_lookback, g.volume_lookback) + 20

    all_metrics = []
    for etf in etf_set:
        close_hist = g.pool_close_history.get(etf)
        vol_hist = g.pool_volume_history.get(etf)
        if close_hist is None or vol_hist is None:
            continue
        hist_closes = np.array(close_hist[-lookback:], dtype=float)
        hist_volumes = np.array(vol_hist[-lookback:], dtype=float)
        valid_mask = (~np.isnan(hist_volumes)) & (hist_volumes > 0)
        hist_closes = hist_closes[valid_mask]
        hist_volumes = hist_volumes[valid_mask]
        if len(hist_closes) < max(g.lookback_days, g.short_momentum_lookback):
            continue

        current_price = _get_adjusted_price(etf, data)
        if current_price is None or current_price <= 0:
            continue

        try:
            today_vol = data[etf].volume if hasattr(data[etf], 'volume') else 0
        except:
            today_vol = 0
        metrics = _calculate_all_metrics(etf, hist_closes, hist_volumes, current_price, today_vol, context)
        if metrics:
            all_metrics.append(metrics)

    for item in all_metrics:
        s = item.get('momentum_score')
        if s is None or (isinstance(s, float) and np.isnan(s)):
            item['momentum_score'] = float('-inf')
        ss = item.get('short_momentum_score')
        if ss is None or (isinstance(ss, float) and np.isnan(ss)):
            item['short_momentum_score'] = float('-inf')

    all_metrics.sort(key=lambda x: x.get(score_key, float('-inf')), reverse=True)

    log.info("[第一步] 全池按%s动量得分排序, 前10:" % ('短期' if use_short else ''))
    for m in all_metrics[:10]:
        log.info("  %s: 动量=%.4f, 短期=%.4f, R2=%.3f, 量比=%s, 拉普=%.4f, 高斯=%.4f" % (
            m['etf'], m['momentum_score'], m['short_momentum_score'],
            m['r_squared'] if m.get('r_squared') else 0,
            "%.2f" % m['volume_ratio'] if m['volume_ratio'] is not None else "N/A",
            m['laplace_slope'], m['gaussian_slope']))

    filtered_list = _apply_filters(all_metrics)
    filtered_list.sort(key=lambda x: x.get(score_key, float('-inf')), reverse=True)
    top_10 = filtered_list[:10]

    log.info("[第二步] 过滤后前10:")
    for m in top_10:
        log.info("  %s: %s=%.4f" % (m['etf'], score_key, m.get(score_key, 0)))

    if not top_10:
        log.info("[第二步] 无符合条件的标的")
        return []

    if len(top_10) >= g.holdings_num:
        ref_score = top_10[g.holdings_num - 1].get(score_key, float('-inf'))
        threshold = ref_score * g.score_threshold_ratio
        candidate_pool = [item for item in top_10 if item.get(score_key, float('-inf')) >= threshold]
        log.info("[第三步] 得分>=第%d名(%.4f)*%.1f=%.4f, 候选%d只" % (
            g.holdings_num, ref_score, g.score_threshold_ratio, threshold, len(candidate_pool)))
    else:
        candidate_pool = top_10[:]
        log.info("[第三步] 前10不足%d只，全部作为候选池" % g.holdings_num)

    positions = get_positions()
    current_holdings = [sec for sec, pos in positions.items() if pos.total_amount > 0]
    log.info("[第四步] 当前持仓: %s" % str(current_holdings))

    candidate_dict = {item['etf']: item for item in candidate_pool}
    retained = [candidate_dict[etf] for etf in current_holdings if etf in candidate_dict]

    if len(retained) >= g.holdings_num:
        retained_sorted = sorted(retained, key=lambda x: x.get(score_key, float('-inf')), reverse=True)
        final_result = retained_sorted[:g.holdings_num]
        log.info("[第四步] 保留持仓%d只>=目标%d, 取前%d" % (len(retained), g.holdings_num, g.holdings_num))
    else:
        need = g.holdings_num - len(retained)
        remaining = [item for item in candidate_pool if item['etf'] not in {r['etf'] for r in retained}]
        additional = remaining[:need]
        final_result = retained + additional
        log.info("[第四步] 保留%d只, 补充%d只" % (len(retained), len(additional)))

    log.info("[最终目标] 共%d只:" % len(final_result))
    for i, item in enumerate(final_result):
        log.info("  %d. %s %s=%.4f" % (i + 1, item['etf'], score_key, item.get(score_key, 0)))

    return final_result


# ==================== 辅助函数 ====================
def _get_adjusted_price(etf, data):
    try:
        raw_price = data[etf].price
        if raw_price is None or raw_price <= 0:
            return None
        fq = g.fq_factor.get(etf, 1.0)
        return raw_price * fq
    except:
        return None


def _split_order(etf, amount):
    if amount == 0:
        return
    direction = 1 if amount > 0 else -1
    remaining = abs(amount)
    while remaining > 0:
        batch = min(remaining, 900000)
        batch = int(batch / 100) * 100
        if batch > 0:
            order(etf, direction * batch)
            remaining -= batch
        else:
            if remaining > 0:
                order(etf, direction * remaining)
            break


# ==================== 交易执行 ====================
def _execute_sell_trades(context, data, final_list):
    log.info("=" * 40 + " 卖出操作 " + "=" * 40)
    target_etfs = []
    if final_list:
        for metrics in final_list[:g.holdings_num]:
            target_etfs.append(metrics['etf'])
            log.info("最终目标: %s" % metrics['etf'])
    else:
        if g.defensive_etf:
            target_etfs = [g.defensive_etf]
            log.info("防御模式: %s" % g.defensive_etf)
        else:
            log.info("无目标(空仓模式)")

    g.target_etfs_list = target_etfs
    target_set = set(target_etfs)

    positions = get_positions()
    sell_count = 0
    for security, pos in positions.items():
        if pos.total_amount > 0 and security not in target_set:
            sell_amount = pos.enable_amount
            if sell_amount <= 0:
                log.info("%s: T+1不可卖" % security)
                continue
            _split_order(security, -sell_amount)
            sell_count += 1
            log.info("卖出: %s, 数量: %d" % (security, sell_amount))

    log.info("本次卖出%d只" % sell_count)


def _execute_buy_trades(context, data, final_list):
    log.info("=" * 40 + " 买入操作 " + "=" * 40)
    target_etfs = g.target_etfs_list
    if not target_etfs:
        log.info("无目标标的，保持空仓")
        return

    positions = get_positions()
    current_holdings = set(sec for sec, pos in positions.items() if pos.total_amount > 0)
    etfs_to_buy = [etf for etf in target_etfs if etf not in current_holdings]

    actual_count = len(current_holdings)
    max_buy = max(0, g.holdings_num - actual_count)
    num_to_buy = min(len(etfs_to_buy), max_buy)

    if num_to_buy <= 0:
        log.info("持仓数(%d)已达目标(%d)，无需买入" % (actual_count, g.holdings_num))
        return

    etfs_to_buy = etfs_to_buy[:num_to_buy]
    available_cash = context.portfolio.cash
    allocated_per_etf = available_cash // num_to_buy

    log.info("可用现金: %.2f, 每只分配: %.2f, 计划买入: %d只" % (
        available_cash, allocated_per_etf, num_to_buy))

    if allocated_per_etf < g.min_money:
        log.info("单只分配%.2f < 最小交易额%.2f，无法买入" % (allocated_per_etf, g.min_money))
        return

    for i, etf in enumerate(etfs_to_buy):
        target_value = allocated_per_etf
        if i == len(etfs_to_buy) - 1:
            target_value = context.portfolio.cash

        price = _get_adjusted_price(etf, data)
        if price is None or price <= 0:
            log.info("%s: 无法获取价格，跳过" % etf)
            continue

        buy_amount = int(target_value / price / 100) * 100
        if buy_amount <= 0:
            buy_amount = 100

        trade_value = buy_amount * price
        if trade_value < g.min_money:
            log.info("%s: 交易额%.2f < 最小%.2f，跳过" % (etf, trade_value, g.min_money))
            continue

        _split_order(etf, buy_amount)
        log.info("买入: %s, 数量: %d, 价格: %.3f" % (etf, buy_amount, price))


# ==================== 止损函数 ====================
def _minute_level_stop_loss(context, data):
    if not g.use_fixed_stop_loss:
        return
    positions = get_positions()
    for security, pos in positions.items():
        if pos.total_amount <= 0 or pos.enable_amount <= 0:
            continue
        current_price = _get_adjusted_price(security, data)
        if current_price is None or current_price <= 0:
            continue
        cost_price = pos.cost_basis
        if cost_price <= 0:
            continue
        if current_price <= cost_price * g.fixedStopLossThreshold:
            loss_pct = (current_price / cost_price - 1) * 100
            log.info("[固定止损] %s 触发, 亏损: %.2f%%" % (security, loss_pct))
            sell_amount = pos.enable_amount
            _split_order(security, -sell_amount)
            if g.enable_stop_loss_trigger:
                g.stop_loss_triggered_today = True


def _minute_level_pct_stop_loss(context, data):
    if not g.use_pct_stop_loss:
        return
    current_date = context.blotter.current_dt.date()
    if g.cache_date != current_date:
        g.yesterday_close_cache = {}
        g.cache_date = current_date

    positions = get_positions()
    for security, pos in positions.items():
        if pos.total_amount <= 0 or pos.enable_amount <= 0:
            continue
        yesterday_close = g.yesterday_close_cache.get(security)
        if yesterday_close is None:
            close_hist = g.pool_close_history.get(security)
            if close_hist and len(close_hist) >= 1:
                yesterday_close = close_hist[-1]
                fq = g.fq_factor.get(security, 1.0)
                yesterday_close = yesterday_close * fq
                g.yesterday_close_cache[security] = yesterday_close
            else:
                continue
        if yesterday_close <= 0:
            continue
        current_price = _get_adjusted_price(security, context)
        if current_price is None or current_price <= 0:
            continue
        stop_price = yesterday_close * g.pct_stop_loss_threshold
        if current_price <= stop_price:
            daily_loss = (current_price / yesterday_close - 1) * 100
            log.info("[跌幅止损] %s 触发, 当日跌幅: %.2f%%" % (security, daily_loss))
            sell_amount = pos.enable_amount
            _split_order(security, -sell_amount)
            if g.enable_stop_loss_trigger:
                g.stop_loss_triggered_today = True