# -*- coding: utf-8 -*-
# ETF五福闹新春 v4.3 - PTrade版本
#
# 迁移自聚宽策略：【五福闹新春】v4.3-完全体动态池的实现
# 原作者：烟花三月ETF (https://www.joinquant.com/post/69750)
#
# 【v1.1】对比聚宽源码后修复收敛
# - g.risk_benchmark 修正为 .SS 格式（get_history 需要）
# - safe_sell 添加停牌/涨跌停检查，移除零股卖出
# - 冷却期改用 get_trade_days 计算交易日（而非日历日）
# - range_bound_start_date 设为前一交易日（消除1天偏移）
# - previous_drawdown 仅在数据充足时赋值
# - avg_etf_money_threshold 改为 None（动态计算）
# - 流动性阈值对齐聚宽（fallback 10M，数据预取在阈值计算前）
# - 预取扩展池数据避免排挤循环

import numpy as np
import math

# ==================== 路径诊断代码（调试导入问题）====================
def _diagnose_import_paths(context=None):
    """诊断导入路径问题（仅用于调试）"""
    log.info("=" * 70)
    log.info("=== 路径诊断开始 ===")
    log.info("=" * 70)

    # 1. 打印回测/实盘模式
    try:
        is_real = is_trade()
        log.info("[诊断] 运行模式: %s" % ("实盘" if is_real else "回测"))
    except Exception as e:
        log.info("[诊断] is_trade() 调用失败: %s" % str(e))

    # 2. 打印 sys.path（Python 导入搜索路径）
    try:
        import sys
        log.info("[诊断] sys.path 路径列表:")
        for i, p in enumerate(sys.path):
            log.info("  [%d] %s" % (i, p))
    except Exception as e:
        log.info("[诊断] sys.path 获取失败: %s" % str(e))

    # 3. 打印当前工作目录
    try:
        import os
        cwd = os.getcwd()
        log.info("[诊断] 当前工作目录: %s" % cwd)
    except Exception as e:
        log.info("[诊断] os.getcwd() 失败: %s" % str(e))

    # 4. 打印 get_research_path()（仅实盘模式）
    if context is None:
        log.info("[诊断] context 未传入，无法调用 get_research_path()")
    else:
        try:
            research_path = get_research_path()
            log.info("[诊断] get_research_path() 返回: %s" % research_path)

            # 尝试扫描该路径下的文件
            try:
                import os
                if os.path.exists(research_path):
                    files = os.listdir(research_path)
                    log.info("[诊断] 研究路径下文件列表 (%d 个):" % len(files))
                    for f in sorted(files)[:20]:  # 只打印前20个
                        log.info("  - %s" % f)
                    if len(files) > 20:
                        log.info("  ... 还有 %d 个文件" % (len(files) - 20))

                    # 检查是否有 shared_position_validator.py
                    validator_file = 'shared_position_validator.py'
                    if validator_file in files:
                        log.info("[诊断] ✓ 找到 %s 在研究路径下" % validator_file)
                    else:
                        log.info("[诊断] ✗ 未找到 %s 在研究路径下" % validator_file)
                else:
                    log.info("[诊断] 研究路径不存在: %s" % research_path)
            except Exception as e:
                log.info("[诊断] 扫描研究路径失败: %s" % str(e))
        except Exception as e:
            log.info("[诊断] get_research_path() 调用失败: %s" % str(e))

    # 5. 尝试导入 shared_position_validator
    log.info("[诊断] 尝试导入 shared_position_validator...")
    try:
        import shared_position_validator
        log.info("[诊断] ✓ 导入成功！模块路径: %s" % shared_position_validator.__file__)
        log.info("[诊断] 模块属性: %s" % dir(shared_position_validator))
    except ImportError as e:
        log.info("[诊断] ✗ ImportError: %s" % str(e))
    except Exception as e:
        log.info("[诊断] ✗ 其他导入错误: %s" % str(e))

    # 6. 尝试从相对路径导入
    log.info("[诊断] 尝试 from .shared_position_validator import...")
    try:
        from .shared_position_validator import validate_strategy_positions
        log.info("[诊断] ✓ 相对导入成功！")
    except ImportError as e:
        log.info("[诊断] ✗ 相对导入失败: %s" % str(e))
    except Exception as e:
        log.info("[诊断] ✗ 其他错误: %s" % str(e))

    log.info("=" * 70)
    log.info("=== 路径诊断结束 ===")
    log.info("=" * 70)


# ==================== 策略初始化 ====================
def initialize(context):
    """初始化策略（设置参数、全局变量）"""
    log.info("=" * 70)
    log.info("=== ETF五福闹新春 v4.3 PTrade版 初始化 ===")
    log.info("=" * 70)

    # ==================== 调用路径诊断 ====================
    _diagnose_import_paths(context)

    set_benchmark("510300.XSHG")

    # ==================== 固定池（114只，代码格式：.SS=上交所，.SZ=深交所）====================
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
        '512050.SS',   # A500E
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
        '159363.SZ',   # 创业板人工智能ETF华宝
        '588170.SS',   # 科创半导
        '159755.SZ',   # 电池ETF
        '512170.SS',   # 医疗ETF
        '512800.SS',   # 银行ETF
        '159819.SZ',   # 人工智能ETF易方达
        '512710.SS',   # 军工龙头
        '159638.SZ',   # 高端装备ETF嘉实
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
        '515120.SS',   # 创新药
        '159566.SZ',   # 储能电池ETF易方达
        '515050.SS',   # 5GETF
        '516510.SS',   # 云计算ETF
        '159256.SZ',   # 创业板软件ETF华夏
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
        '159840.SZ',   # 锂电池ETF工银
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

    # ==================== 静态扩展池（补充高流动性ETF，替代全市场扫描）====================
    g.extended_etf_pool = [
        # ===== 补充宽基指数ETF =====
        '510050.SS',   # 上证50ETF华夏
        '510180.SS',   # 上证180ETF华夏
        '510300.SS',   # 沪深300ETF华泰柏瑞 (已有510300.SS在固定池，去重会处理)
        '510330.SS',   # 沪深300ETF华夏
        '510500.SS',   # 中证500ETF华夏
        '510880.SS',   # 上证红利ETF
        '512100.SS',   # 中证1000ETF
        '512010.SS',   # 上证综指ETF
        '512660.SS',   # 军工ETF
        '512690.SS',   # 酒ETF
        '512800.SS',   # 银行ETF
        '512980.SS',   # 医疗ETF
        '159901.SZ',   # 深证100ETF易方达
        '159903.SZ',   # 深证成指ETF
        '159905.SZ',   # 深证红利ETF
        '159915.SZ',   # 创业板ETF易方达
        '159919.SZ',   # 沪深300ETF嘉实
        '159922.SZ',   # 中证500ETF嘉实
        '159933.SZ',   # 中证1000ETF
        '159949.SZ',   # 创业板ETF
        '159966.SZ',   # 创业板50ETF
        '159974.SZ',   # 创成长ETF
        '159975.SZ',   # 创低波ETF
        '159601.SZ',   # 中证A50ETF
        '159605.SZ',   # 中证A500ETF
        '159608.SZ',   # 创业板200ETF
        '159611.SZ',   # 中证A100ETF
        '159552.SZ',   # 中证2000ETF
        '159555.SZ',   # 中证2000ETF华夏
        '159521.SZ',   # 中证A500ETF景顺
        '159851.SZ',   # 双创50ETF
        '159863.SZ',   # 双创ETF银华
        '159781.SZ',   # 科创创业50ETF
        '560050.SS',   # A50ETF基金
        '560110.SS',   # 中证A500ETF华泰
        '560160.SS',   # 中证A500ETF博时
        '588000.SS',   # 科创50ETF
        '588030.SS',   # 科创50ETF易方达
        '588050.SS',   # 科创50ETF华夏
        '588100.SS',   # 科创100ETF
        '588200.SS',   # 科创200ETF
        # ===== 补充行业/主题ETF =====
        '515000.SS',   # 科技ETF
        '515010.SS',   # 稀土ETF
        '515030.SS',   # 新能源车ETF华夏
        '515050.SS',   # 5GETF华夏
        '515060.SS',   # 半导体ETF国联安
        '515070.SS',   # 非银ETF
        '515100.SS',   # 智能汽车ETF
        '515110.SS',   # 汽车ETF
        '515120.SS',   # 创新药ETF
        '515150.SS',   # 煤炭ETF
        '515170.SS',   # 食品饮料ETF
        '515180.SS',   # 银行ETF华宝
        '515190.SS',   # 银行ETF鹏华
        '515200.SS',   # 房地产ETF
        '515220.SS',   # 煤炭ETF国泰
        '515230.SS',   # 钢铁ETF
        '515240.SS',   # 机械设备ETF
        '515250.SS',   # 智能制造ETF
        '515260.SS',   # 消费ETF华夏
        '515270.SS',   # 电池ETF
        '515280.SS',   # 环保ETF
        '515290.SS',   # 有色ETF华夏
        '515330.SS',   # 信息技术ETF华夏
        '515340.SS',   # 软件ETF
        '515360.SS',   # 人工智能ETF
        '515370.SS',   # 机器人ETF
        '515380.SS',   # 网络游戏ETF
        '515390.SS',   # 通信ETF
        '515400.SS',   # 大数据ETF
        '515440.SS',   # 光伏ETF
        '515450.SS',   # 半导体ETF华夏
        '515460.SS',   # 军工ETF易方达
        '515470.SS',   # 军工ETF广发
        '515480.SS',   # 半导体ETF国联
        '515490.SS',   # 半导体ETF嘉实
        '515520.SS',   # 金ETF
        '515530.SS',   # 新基建ETF
        '515540.SS',   # 证券ETF华宝
        '515550.SS',   # 证券ETF华夏
        '515560.SS',   # 证券ETF易方达
        '515570.SS',   # 证券ETF国泰
        '515580.SS',   # 证券ETF鹏华
        '515590.SS',   # 证券ETF富国
        '515610.SS',   # 新能源ETF华夏
        '515710.SS',   # 食品ETF华夏
        '515730.SS',   # 食品ETF华宝
        '515880.SS',   # 通信ETF华夏
        '516010.SS',   # 新能源车ETF华泰
        '516020.SS',   # 半导体材料ETF
        '516050.SS',   # 化工ETF
        '516060.SS',   # 新材料ETF
        '516070.SS',   # 电子ETF
        '516150.SS',   # 红色电力ETF
        '516160.SS',   # 新能源车ETF国泰
        '516180.SS',   # 风电ETF
        '516260.SS',   # 电池ETF华泰
        '516280.SS',   # 新能源车ETF广发
        '516390.SS',   # 化工龙头ETF
        '516400.SS',   # 有色60ETF
        '516590.SS',   # 建筑ETF
        '516620.SS',   # 传媒ETF
        '516660.SS',   # 畜牧养殖ETF
        '516670.SS',   # 畜牧ETF国泰
        '516730.SS',   # 机械ETF
        '516770.SS',   # 军工ETF华泰
        '516850.SS',   # 新能源车ETF
        '516880.SS',   # 光伏产业ETF
        '516950.SS',   # 基建ETF
        '159616.SZ',   # 家电ETF
        '159632.SZ',   # 消费电子ETF
        '159633.SZ',   # 半导体ETF
        '159655.SZ',   # 标普500ETF华夏
        '159666.SZ',   # 畜牧ETF
        '159688.SZ',   # 科创芯片ETF
        '159822.SZ',   # 有色金属ETF
        '159855.SZ',   # 光伏龙头ETF
        '159939.SZ',   # 信息技术ETF
        '161128.SZ',   # 标普信息科技LOF
        '561260.SS',   # 央企红利ETF
        '562010.SS',   # 绿色电力ETF
        '562880.SS',   # 证券ETF基金
        '159607.SZ',   # 中概互联网ETF
        # ===== 补充港股/海外ETF =====
        '513050.SS',   # 港股通50ETF
        '513060.SS',   # 恒生医疗ETF
        '513010.SS',   # 港股互联网ETF
        '513070.SS',   # 港股通ETF
        '513130.SS',   # 恒生科技ETF
        '159740.SZ',   # 恒生科技ETF嘉实
        '159741.SZ',   # 恒生科技指数ETF
        '513530.SS',   # 德国DAXETF
        # ===== 补充MSCI ETF =====
        '512990.SS',   # MSCI中国A50ETF
        '159904.SZ',   # MSCI中国ETF
        '159620.SZ',   # MSCI中国A50ETF招商
        # ===== 补充红利/价值ETF =====
        '512090.SS',   # 红利ETF鹏华
        '159581.SZ',   # 红利低波ETF
        '159582.SZ',   # 红利低波100ETF
        '562060.SS',   # 中证红利ETF华泰
        '512560.SS',   # 红利低波ETF创金
    ]

    g.filtered_fixed_pool = []           # 过滤后的固定池
    g.dynamic_etf_pool = []              # 动态池
    g.merged_etf_pool = []               # 合并后的池
    g.ranked_etfs_result = []            # 动量计算结果
    g.positions = {}                     # 持仓记录
    g.target_etfs_list = []              # 目标列表
    g.cache_date = None                  # 缓存日期（用于止损）
    g.yesterday_close_cache = {}         # 昨日收盘价缓存（用于止损）

    # ==================== 策略核心参数 ====================
    g.holdings_num = 1                   # 持仓数量
    g.defensive_etf = "511880.SS"        # 防御型ETF（银华日利）
    g.min_money = 10                     # 最小交易金额（元）
    g.max_order_shares = 900000          # 单笔最大下单股数

    # 动量计算参数（25天周期，0-5分阈值）
    g.lookback_days = 25                 # 动量计算回看天数
    g.min_score_threshold = 0            # 动量得分下限
    g.max_score_threshold = 5            # 动量得分上限
    g.score_threshold_ratio = 0.9        # 候选池得分比例

    # 短期动量参数（21天周期，0-6分阈值）
    g.use_short_momentum_period = False  # 短期动量过滤开关
    g.short_momentum_lookback = 21       # 短期动量回看天数
    g.short_momentum_min_score = 0       # 短期动量得分下限
    g.short_momentum_max_score = 6       # 短期动量得分上限

    # 过滤开关及参数
    g.enable_r2_filter = True            # R²过滤开关
    g.r2_threshold = 0.4                 # R²阈值
    g.enable_volume_check = True         # 成交量过滤开关
    g.volume_lookback = 5                # 成交量回看天数
    g.volume_threshold = 1.8             # 成交量比阈值
    g.enable_loss_filter = True          # 短期风控过滤开关
    g.loss = 0.97                        # 单日最大允许跌幅（3%）
    g.enable_premium_filter = False      # 溢价率过滤（PTrade无NAV API，始终禁用）
    g.max_premium_rate = 30              # 最大允许溢价率（%）

    # 滤波器参数（正常期=拉普拉斯，震荡期=高斯）
    g.laplace_s_param = 0.05             # 拉普拉斯衰减率
    g.laplace_min_slope = 0.002          # 拉普拉斯斜率阈值
    g.gaussian_sigma = 1.2               # 高斯标准差
    g.gaussian_min_slope = 0.002         # 高斯斜率阈值

    # ==================== 震荡期参数 ====================
    g.enable_range_bound_mode = True     # 震荡期模式开关
    g.current_filter = '正常期'          # 当前滤波器
    g.risk_state = '正常期'              # 风险状态
    g.lookback_high_low_days = 20        # 近20个交易日
    g.risk_benchmark = '510300.SS'       # 风险基准ETF（沪深300ETF，get_history需.SS格式）

    # 进入震荡期条件
    g.enable_bias_trigger = True         # 乖离率过大触发
    g.bias_threshold = 0.08              # 乖离率阈值（8%）
    g.ma_period = 20                     # 均线周期
    g.enable_rsi_trigger = True          # RSI超买回落触发
    g.rsi_overbought = 70               # RSI超买阈值
    g.rsi_pullback = 65                  # RSI回落阈值
    g.previous_rsi = None                # 前一日RSI
    g.enable_stop_loss_trigger = True    # 止损触发进入震荡期
    g.stop_loss_triggered_today = False  # 今日是否触发止损

    # 退出震荡期条件
    g.enable_low_point_rise_trigger = True   # 从低点上涨触发
    g.low_point_rise_threshold = 0.04        # 上涨阈值（4%）
    g.enable_stable_signal_trigger = True    # 企稳信号触发
    g.drawdown_recovery = 0.02               # 回撤收窄阈值（2%）
    g.max_range_bound_days = 20              # 最大震荡期天数
    g.stable_days = 0                        # 企稳天数计数

    # 震荡期控制
    g.filter_switch_cooldown = 3         # 切换冷却期（3天）
    g.last_switch_date = None            # 上次切换日期
    g.range_bound_start_date = None      # 震荡期开始日期
    g.range_bound_days_count = 0         # 震荡期天数计数

    # 风险监控数据
    g.previous_drawdown = None           # 前一日回撤值
    g.max_portfolio_value = 0            # 策略净值最高点
    g.drawdown_threshold = 0.03          # 回撤监控阈值（3%）

    # 止损参数
    g.use_fixed_stop_loss = True         # 固定比例止损开关
    g.fixedStopLossThreshold = 0.95      # 固定止损比例（5%）
    g.use_pct_stop_loss = False          # 当日跌幅止损开关
    g.pct_stop_loss_threshold = 0.95     # 当日跌幅止损比例

    # 流动性阈值（动态计算，与聚宽一致）
    g.avg_etf_money_threshold = None

    # 标志位
    g.afternoon_done = False             # 午后交易是否已执行
    g.skip_today = False                 # 交易时间启动跳过今日
    g.first_day = True                   # 首次运行标志
    g.name_cache = {}                    # 名称缓存

    # 预取数据容器
    g.benchmark_closes = None            # 基准收盘价
    g.benchmark_highs = None             # 基准最高价
    g.benchmark_lows = None              # 基准最低价
    g.hist_closes = {}                   # {code: close_array}
    g.hist_volumes = {}                  # {code: volume_array}
    g.hist_money = {}                    # {code: money_array}
    g.pool_money_data = {}              # {code: money_array} 全池流动性预取
    g.yesterday_close_map = {}           # 持仓昨日收盘价

    # 启动校验：去除扩展池与固定池重叠
    fixed_set = set(g.fixed_etf_pool)
    overlap = [c for c in g.extended_etf_pool if c in fixed_set]
    if overlap:
        log.info("[初始化] 去除扩展池与固定池重叠: %d只" % len(overlap))
        g.extended_etf_pool = [c for c in g.extended_etf_pool if c not in fixed_set]

    # 回测配置
    if not is_trade():
        set_backtest()

    log.info("[参数] 持仓数量: %d, 防御ETF: %s" % (g.holdings_num, g.defensive_etf))
    log.info("[参数] 动量周期: %d天, 得分阈值: [%.1f, %.1f]" % (
        g.lookback_days, g.min_score_threshold, g.max_score_threshold))
    log.info("[参数] R²过滤: %s (%.1f), 成交量过滤: %s (%.1f)" % (
        g.enable_r2_filter, g.r2_threshold, g.enable_volume_check, g.volume_threshold))
    log.info("[参数] 短期风控: %s (%.0f%%), 溢价率: %s" % (
        g.enable_loss_filter, (1 - g.loss) * 100, g.enable_premium_filter))
    log.info("[参数] 震荡期: %s, 止损: 固定%s 跌幅%s" % (
        g.enable_range_bound_mode, g.use_fixed_stop_loss, g.use_pct_stop_loss))
    log.info("[参数] 固定池: %d只, 扩展池: %d只" % (
        len(g.fixed_etf_pool), len(g.extended_etf_pool)))
    log.info("=" * 70)


def set_backtest():
    """回测配置"""
    set_limit_mode('UNLIMITED')
    set_commission(commission_ratio=0.0001, min_commission=5, type="STOCK")
    set_slippage(PriceRelatedSlippage(0.0001))


# ==================== 盘前处理 ====================
def before_trading_start(context, data):
    """盘前数据预取 + 晨间流水线"""
    # 重置每日标志
    g.afternoon_done = False
    g.stop_loss_triggered_today = False
    g.cache_date = None
    g.yesterday_close_cache = {}

    # 盘前启动检测（v5.8模式）
    bts_hour = context.blotter.current_dt.hour
    bts_minute = context.blotter.current_dt.minute
    is_trading_time = (bts_hour == 9 and bts_minute >= 30) or bts_hour >= 10
    if is_trading_time:
        g.skip_today = True
        log.info("[盘前] 交易时间启动，跳过今日")
        return
    g.skip_today = False

    log.info("★" * 40)
    log.info("▶️ 【晨间流水线】启动...")

    try:
        # 步骤1：持仓检查
        log.info("【持仓检查】检查当前持仓状态...")
        check_positions(context, data)

        # 步骤2：回撤监控
        log.info("【回撤监控】监控策略回撤...")
        monitor_drawdown(context)

        # 步骤3：预取风险基准历史数据（用于震荡期判断）
        log.info("【数据预取】预取风险基准历史数据...")
        _prefetch_benchmark_data(context)

        # 步骤4：预取全池流动性数据（固定池+扩展池，用于阈值计算和池过滤）
        log.info("【数据预取】预取全池流动性数据...")
        _prefetch_liquidity_data(context)

        # 步骤5：首次运行初始化震荡期状态
        if g.first_day:
            g.first_day = False
            init_range_bound_status(context)

        # 步骤6：流动性阈值计算（使用步骤4预取的数据）
        log.info("【流动性阈值】计算ETF流动性阈值...")
        calculate_global_etf_threshold(context)

        # 步骤7：动态池更新（静态扩展池+流动性过滤）
        log.info("【动态池更新】更新动态池...")
        update_sector_pool(context)

        # 步骤8：固定池流动性过滤
        log.info("【固定池过滤】过滤固定池流动性...")
        filter_fixed_pool_by_volume(context)

        # 步骤9：合并池
        log.info("【合并池】合并固定池与动态池...")
        daily_merge_etf_pools(context)

        # 步骤10：订阅合并池 + 持仓代码（止损需 data[code].price）
        subscribe_list = g.merged_etf_pool[:]
        for code, pos in context.portfolio.positions.items():
            if pos.amount > 0 and code not in subscribe_list:
                subscribe_list.append(code)
        if subscribe_list:
            set_universe(subscribe_list)

        # 步骤11：预取合并池历史数据（用于动量计算）
        log.info("【数据预取】预取合并池历史数据...")
        _prefetch_pool_history_data(context)

        # 步骤12：预取持仓昨日收盘价（用于止损）
        _prefetch_position_yesterday_close(context)

    except Exception as e:
        log.warning("【晨间流水线】异常: %s" % str(e))

    log.info("⏸️ 【晨间流水线】执行完毕！")


def _prefetch_benchmark_data(context):
    """预取风险基准历史数据"""
    try:
        lookback = max(g.ma_period, g.lookback_high_low_days) + 30
        # 收盘价
        his = get_history(lookback, frequency='1d', field='close',
                          security_list=g.risk_benchmark, fq='pre',
                          include=False, is_dict=True)
        if his and g.risk_benchmark in his:
            arr = his[g.risk_benchmark]['close']
            if len(arr) > 0:
                g.benchmark_closes = np.array(arr, dtype=float)

        # 最高价
        his_h = get_history(lookback, frequency='1d', field='high',
                            security_list=g.risk_benchmark, fq='pre',
                            include=False, is_dict=True)
        if his_h and g.risk_benchmark in his_h:
            arr = his_h[g.risk_benchmark]['high']
            if len(arr) > 0:
                g.benchmark_highs = np.array(arr, dtype=float)

        # 最低价
        his_l = get_history(lookback, frequency='1d', field='low',
                            security_list=g.risk_benchmark, fq='pre',
                            include=False, is_dict=True)
        if his_l and g.risk_benchmark in his_l:
            arr = his_l[g.risk_benchmark]['low']
            if len(arr) > 0:
                g.benchmark_lows = np.array(arr, dtype=float)

    except Exception as e:
        log.warning("【数据预取】基准数据预取失败: %s" % str(e))


def _prefetch_liquidity_data(context):
    """预取固定池+扩展池的3日成交额（批量模式，减少API调用）
    解决数据依赖链bug：确保扩展池ETF始终有数据可评估，避免排挤循环"""
    g.pool_money_data = {}  # {code: 3日money数组}
    all_static_pool = list(set(g.fixed_etf_pool + g.extended_etf_pool))
    log.info("[流动性预取] 需预取%d只标的的3日成交额" % len(all_static_pool))

    try:
        his = get_history(3, frequency='1d', field='money',
                          security_list=all_static_pool, fq='pre',
                          include=False, is_dict=True)
        if his:
            for code in all_static_pool:
                if code in his:
                    arr = his[code]['money']
                    if len(arr) > 0:
                        g.pool_money_data[code] = np.array(arr, dtype=float)
    except Exception as e:
        log.warning("[流动性预取] 批量获取失败: %s，尝试逐个获取" % str(e))
        for code in all_static_pool:
            try:
                his = get_history(3, frequency='1d', field='money',
                                  security_list=code, fq='pre',
                                  include=False, is_dict=True)
                if his and code in his:
                    arr = his[code]['money']
                    if len(arr) > 0:
                        g.pool_money_data[code] = np.array(arr, dtype=float)
            except Exception:
                continue

    log.info("[流动性预取] 成功获取%d只标的的成交额数据（失败%d只）" % (
        len(g.pool_money_data), len(all_static_pool) - len(g.pool_money_data)))


def _prefetch_pool_history_data(context):
    """预取合并池的历史收盘价、成交量、成交额（批量模式）"""
    if not g.merged_etf_pool:
        log.warning("【数据预取】合并池为空")
        return

    lookback = max(g.lookback_days, g.short_momentum_lookback, g.volume_lookback) + 20
    g.hist_closes = {}
    g.hist_volumes = {}
    g.hist_money = {}
    pool = g.merged_etf_pool

    # 批量获取收盘价（1次API调用）
    try:
        his_c = get_history(lookback, frequency='1d', field='close',
                            security_list=pool, fq='pre',
                            include=False, is_dict=True)
        if his_c:
            for code in pool:
                if code in his_c:
                    arr = his_c[code]['close']
                    if len(arr) > 0:
                        g.hist_closes[code] = np.array(arr, dtype=float)
    except Exception as e:
        log.warning("[数据预取] 收盘价批量获取失败: %s" % str(e))

    # 批量获取成交量（1次API调用）
    try:
        his_v = get_history(lookback, frequency='1d', field='volume',
                            security_list=pool, fq='pre',
                            include=False, is_dict=True)
        if his_v:
            for code in pool:
                if code in his_v:
                    arr = his_v[code]['volume']
                    if len(arr) > 0:
                        g.hist_volumes[code] = np.array(arr, dtype=float)
    except Exception as e:
        log.warning("[数据预取] 成交量批量获取失败: %s" % str(e))

    # 成交额：优先复用 pool_money_data（已预取3日），避免重复API调用
    for code in pool:
        if code in g.pool_money_data:
            g.hist_money[code] = g.pool_money_data[code]
        else:
            try:
                his_m = get_history(3, frequency='1d', field='money',
                                    security_list=code, fq='pre',
                                    include=False, is_dict=True)
                if his_m and code in his_m:
                    arr = his_m[code]['money']
                    if len(arr) > 0:
                        g.hist_money[code] = np.array(arr, dtype=float)
            except Exception:
                continue

    log.info("[数据预取] 收盘价: %d只, 成交量: %d只, 成交额: %d只(复用%d只)" % (
        len(g.hist_closes), len(g.hist_volumes), len(g.hist_money),
        sum(1 for c in pool if c in g.pool_money_data)))


def _prefetch_position_yesterday_close(context):
    """预取持仓昨日收盘价（用于分钟级跌幅止损）"""
    g.yesterday_close_map = {}
    for code, pos in context.portfolio.positions.items():
        if pos.amount > 0:
            try:
                his = get_history(1, frequency='1d', field='close',
                                  security_list=code, fq='pre',
                                  include=False, is_dict=True)
                if his and code in his:
                    arr = his[code]['close']
                    if len(arr) > 0:
                        yclose = float(arr[-1])
                        if yclose > 0:
                            g.yesterday_close_map[code] = yclose
            except Exception:
                pass


# ==================== 分钟回调（时间分发）====================
def handle_data(context, data):
    """分钟回调 - 时间分发"""
    if getattr(g, 'skip_today', False):
        return

    now = context.blotter.current_dt
    time_str = "%02d:%02d" % (now.hour, now.minute)

    # 午后交易流水线 (13:10)
    if time_str == '13:10' and not getattr(g, 'afternoon_done', False):
        afternoon_routine(context, data)
        g.afternoon_done = True
        return

    # 分钟级止损 (09:25-11:30, 13:00-14:57)
    if ('09:25' < time_str < '11:30') or ('13:00' < time_str < '14:57'):
        if g.use_fixed_stop_loss:
            minute_level_stop_loss(context, data)
        if g.use_pct_stop_loss:
            minute_level_pct_stop_loss(context, data)


# ==================== 盘后处理 ====================
def after_trading_end(context, data):
    """收盘后重置标志和缓存"""
    g.cache_date = None
    g.yesterday_close_cache = {}
    g.afternoon_done = False

    # 更新震荡期天数
    if g.current_filter == '震荡期' and g.range_bound_start_date is not None:
        g.range_bound_days_count += 1
        log.info("📊 震荡期已持续 %d 个交易日" % g.range_bound_days_count)

    log.info("🔄 收盘缓存重置完成")


# ==================== 任务流水线 ====================
# NOTE: 晨间流水线逻辑在 before_trading_start() 中执行，无需单独 morning_routine 函数


def afternoon_routine(context, data):
    """午后交易流水线（13:10执行）"""
    log.info("▶️ 【午后交易流水线】启动...")

    log.info("【震荡期退出检查】检查是否需要退出震荡期...")
    check_and_exit_range_bound_mode(context)

    log.info("【震荡期进入检查】检查是否需要进入震荡期...")
    check_and_enter_range_bound_mode(context)

    log.info("【动量计算】计算动量得分与排序...")
    calculate_and_log_ranked_etfs(context, data)

    log.info("【卖出执行】执行卖出操作...")
    execute_sell_trades(context, data)

    log.info("【买入执行】执行买入操作...")
    execute_buy_trades(context, data)

    log.info("⏸️ 【午后交易流水线】执行完毕！")


# ==================== 持仓检查 ====================
def check_positions(context, data):
    """盘前持仓检查"""
    for code, pos in context.portfolio.positions.items():
        if pos.amount > 0:
            name = get_security_name(code)
            price = data[code].price if code in data else pos.avg_cost
            log.info("📊 【持仓检查】%s %s, 数量: %d, 成本: %.3f, 当前价: %.3f" % (
                code, name, pos.amount, pos.avg_cost, price))
            try:
                status = get_stock_status(code, 'HALT')
                if status:
                    log.info("⚠️ %s %s 今日停牌" % (code, name))
            except Exception:
                pass


def monitor_drawdown(context):
    """回撤监控"""
    try:
        current_value = context.portfolio.total_value
        if current_value > g.max_portfolio_value:
            g.max_portfolio_value = current_value
        if g.max_portfolio_value > 0:
            current_drawdown = (g.max_portfolio_value - current_value) / g.max_portfolio_value
            if current_drawdown >= g.drawdown_threshold:
                positions_info = []
                for code, pos in context.portfolio.positions.items():
                    if pos.amount > 0:
                        name = get_security_name(code)
                        positions_info.append("%s:%d股" % (name, pos.amount))
                log.info("【回撤预警】回撤达到 %.2f%% (阈值: %.0f%%)" % (
                    current_drawdown * 100, g.drawdown_threshold * 100))
                log.info("  当前净值: %.0f  |  最高净值: %.0f" % (
                    current_value, g.max_portfolio_value))
                log.info("  当前滤波器: %s  |  风险状态: %s" % (
                    g.current_filter, g.risk_state))
                log.info("  持仓: %s" % (
                    ', '.join(positions_info) if positions_info else '空仓'))
    except Exception as e:
        log.error("【回撤监控】计算异常: %s" % str(e))


# ==================== 流动性阈值计算 ====================
def calculate_global_etf_threshold(context):
    """计算ETF流动性阈值（使用预取的pool_money_data，对齐聚宽逻辑）"""
    log.info("【全局阈值更新】计算ETF流动性门槛")
    try:
        all_pool = list(set(g.fixed_etf_pool + g.extended_etf_pool))
        total_money_3d = 0
        valid_count = 0
        for code in all_pool:
            try:
                if code in g.pool_money_data and len(g.pool_money_data[code]) > 0:
                    total_money_3d += np.sum(g.pool_money_data[code])
                    valid_count += 1
            except Exception:
                continue

        if valid_count > 0:
            # 对齐聚宽逻辑：全市场ETF日均总成交额 / 20000
            # 日均 = 3日总成交额 / 3天 / ETF只数
            avg_daily_per_etf = (total_money_3d / 3.0) / float(valid_count)
            threshold = avg_daily_per_etf / 20000
            g.avg_etf_money_threshold = threshold
        else:
            # 对齐聚宽fallback: 10M
            g.avg_etf_money_threshold = 10000000
            log.info("【全局阈值更新】数据不足(%d只)，使用保守值1000万元" % valid_count)

        log.info("【全局阈值更新完成】有效标的%d只，阈值=%.0f万元" % (
            valid_count, g.avg_etf_money_threshold / 10000))
    except Exception as e:
        log.warning("计算全局阈值异常: %s，使用保守值1000万元" % str(e))
        g.avg_etf_money_threshold = 10000000


# ==================== 动态池更新（静态扩展池+流动性过滤）====================
def _clean_etf_name(original_name):
    """清洗ETF名称：去除基金公司名和噪音词，用于名称分组去重"""
    cleaned = original_name
    # 基金公司名（按长度降序，避免短词误删）
    FUND_COMPANIES = sorted([
        '易方达', '广发', '华夏', '华安', '嘉实', '富国', '招商', '鹏华', '南方', '汇添富', '国泰', '平安',
        '银华', '天弘', '建信', '工银', '华泰柏瑞', '博时', '景顺长城', '景顺', '华宝', '申万菱信', '万家', '中欧',
        '兴证全球', '浙商', '诺安', '前海开源', '泰康', '泰达宏利', '农银汇理', '交银', '东方红', '财通', '华商',
        '国联', '永赢', '金鹰', '德邦', '创金合信', '西部利得', '圆信永丰', '泓德', '汇安', '诺德', '恒生前海',
        '华润元大', '大成', '海富通', '摩根', '华泰', '中信', '中银', '兴全', '国信', '长城', '中金', '浙商证券',
        '东海', '东吴', '浦银安盛', '信达澳亚', '中加', '中航', '中融', '中邮', '中庚', '中信保诚', '中信建投',
        '中银国际', '中银证券', '九泰', '交银施罗德', '光大保德信', '兴银', '农银', '国投瑞银', '国海富兰克林',
        '国联安', '国金', '太平', '方正富邦', '民生加银', '汇丰晋信', '银河', '长信', '长安', '长盛', '长江证券', '鹏扬',
    ], key=len, reverse=True)
    # 噪音词（按长度降序）
    NOISE_WORDS = sorted([
        'ETF基金', 'LOF基金', 'ETF联接', 'LOF联接', '联接基金', '指数基金', '指数ETF',
        'ETF', 'LOF', 'A类', 'C类', 'E类', '指数A', '指数C', 'AH', 'BS', 'CS', 'DB',
        'FG', 'GF', 'GT', 'HGS', 'SG', 'SZ', 'TF', 'TK', 'WJ', 'YH', 'ZS', 'ZZ',
        '联接', '基金', '指基', '指增', '指数', '策略', '精选', '龙头', '量化', '增强',
        '板块', '产业', '主题', '场内', '场外', '上市开放式', '全指', '智能',
        '低波', '基本面', '大', '新', '板块',
    ], key=len, reverse=True)
    for company in FUND_COMPANIES:
        cleaned = cleaned.replace(company, '')
    for noise in NOISE_WORDS:
        cleaned = cleaned.replace(noise, '')
    return cleaned.strip()


def update_sector_pool(context):
    """动态池更新：流动性过滤 + 名称去重"""
    log.info("【动态池更新】开始执行")
    if g.avg_etf_money_threshold is None:
        g.avg_etf_money_threshold = 10000000

    dynamic_threshold = g.avg_etf_money_threshold
    log.info("【动态池更新】使用流动性门槛=日均%.0f万元" % (dynamic_threshold / 10000))

    # 第一步：流动性过滤
    liquidity_qualified = []
    liquidity_removed = []
    money_map = {}
    for code in g.extended_etf_pool:
        try:
            if code in g.pool_money_data and len(g.pool_money_data[code]) > 0:
                avg_money = np.mean(g.pool_money_data[code])
                money_map[code] = avg_money
                if avg_money > dynamic_threshold:
                    liquidity_qualified.append(code)
                else:
                    liquidity_removed.append(code)
            else:
                liquidity_removed.append(code)
        except Exception:
            liquidity_removed.append(code)

    log.info("【动态池更新】扩展池: %d只, 通过流动性: %d只, 剔除: %d只" % (
        len(g.extended_etf_pool), len(liquidity_qualified), len(liquidity_removed)))

    # 第二步：名称去重（对齐聚宽分组去重逻辑）
    # 按清洗后的名称分组，每组保留成交额最大的一只
    name_groups = {}
    cleaned_empty_count = 0
    for code in liquidity_qualified:
        try:
            original_name = get_security_name(code)
            cleaned = _clean_etf_name(original_name)
            if cleaned == '' or len(cleaned) < 2:
                cleaned_empty_count += 1
                continue
            # 用清洗后名称的前2字符作为分组键（简化版，对齐聚宽特别组/普通组的前2字符分组）
            group_key = cleaned[:2] if len(cleaned) >= 2 else cleaned
            if group_key not in name_groups:
                name_groups[group_key] = []
            name_groups[group_key].append({
                'code': code, 'money': money_map.get(code, 0),
                'original_name': original_name, 'cleaned': cleaned
            })
        except Exception:
            continue

    # 每组选取成交额最大的1只
    deduped_pool = []
    for group_key, items in name_groups.items():
        best = max(items, key=lambda x: x['money'])
        deduped_pool.append(best['code'])

    g.dynamic_etf_pool = deduped_pool
    log.info("【动态池更新】名称清洗删除: %d只, 名称分组: %d组, 去重后: %d只" % (
        cleaned_empty_count, len(name_groups), len(deduped_pool)))
    log.info("最终动态池纳入: %d只ETF" % len(g.dynamic_etf_pool))


# ==================== 固定池流动性过滤 ====================
def filter_fixed_pool_by_volume(context):
    """每日对固定池进行流动性过滤"""
    log.info("【固定池过滤】开始执行")
    if not g.fixed_etf_pool:
        log.info("【固定池过滤】固定池为空，跳过")
        return

    if g.avg_etf_money_threshold is None:
        g.avg_etf_money_threshold = 10000000
    dynamic_threshold = g.avg_etf_money_threshold
    log.info("【固定池过滤】使用流动性门槛=日均%.0f万元" % (dynamic_threshold / 10000))

    qualified = []
    removed = []
    for code in g.fixed_etf_pool:
        try:
            if code in g.pool_money_data and len(g.pool_money_data[code]) > 0:
                avg_money = np.mean(g.pool_money_data[code])
                if avg_money > dynamic_threshold:
                    qualified.append(code)
                else:
                    removed.append(code)
            else:
                # 无数据时保留（保守策略）
                qualified.append(code)
        except Exception:
            qualified.append(code)

    if removed:
        log.info("【固定池过滤】剔除低流动性标的(%d只)" % len(removed))

    g.filtered_fixed_pool = qualified
    log.info("【固定池过滤】保留高流动性标的(%d只)" % len(qualified))


# ==================== 合并池 ====================
def daily_merge_etf_pools(context):
    """每日合并固定池和动态池"""
    if not g.filtered_fixed_pool:
        g.filtered_fixed_pool = g.fixed_etf_pool[:]
    merged = list(set(g.filtered_fixed_pool + g.dynamic_etf_pool))
    merged.sort()
    log.info("【合并池统计】固定池: %d只, 动态池: %d只, 合并后: %d只" % (
        len(g.filtered_fixed_pool), len(g.dynamic_etf_pool), len(merged)))
    g.merged_etf_pool = merged


# ==================== 震荡期状态初始化 ====================
def init_range_bound_status(context):
    """首次运行时，判断当前是否处于震荡期"""
    if not g.enable_range_bound_mode:
        return
    log.info("🔍 【首次运行】初始化震荡期状态...")
    try:
        if g.benchmark_closes is None or len(g.benchmark_closes) < max(g.ma_period, g.lookback_high_low_days):
            log.warning("【首次运行】数据不足，保持正常期")
            return

        close = g.benchmark_closes
        high = g.benchmark_highs if g.benchmark_highs is not None else close
        low = g.benchmark_lows if g.benchmark_lows is not None else close

        current_price = close[-1]
        n = min(g.lookback_high_low_days, len(high))
        recent_high = np.max(high[-n:])
        recent_low = np.min(low[-n:])
        ma = np.mean(close[-g.ma_period:])
        bias = (current_price - ma) / ma if ma > 0 else 0
        rise_from_low = (current_price - recent_low) / recent_low if recent_low > 0 else 0
        current_rsi = calculate_rsi(close, period=14)

        should_enter = False
        signals = []
        if g.enable_bias_trigger and bias > g.bias_threshold:
            should_enter = True
            signals.append("乖离率%.2f%%>%.0f%%" % (bias * 100, g.bias_threshold * 100))
        if g.enable_rsi_trigger and current_rsi is not None and len(close) >= 15:
            prev_rsi = calculate_rsi(close[:-1], period=14)
            if prev_rsi is not None and prev_rsi > g.rsi_overbought and current_rsi < g.rsi_pullback:
                should_enter = True
                signals.append("RSI超买回落%.1f→%.1f" % (prev_rsi, current_rsi))

        if should_enter:
            g.current_filter = '震荡期'
            g.risk_state = '震荡期'
            g.range_bound_start_date = _get_previous_trade_date(context)
            g.range_bound_days_count = 0
            log.info("🔔 【首次运行】初始化进入震荡期: %s" % '; '.join(signals))
        else:
            g.current_filter = '正常期'
            g.risk_state = '正常期'
            if len(close) >= g.lookback_high_low_days:
                g.previous_drawdown = (recent_high - current_price) / recent_high if recent_high > 0 else 0
            g.previous_rsi = current_rsi
            log.info("📌 【首次运行】初始状态: 正常期(拉普拉斯), 乖离率: %.2f%%, RSI: %.1f" % (
                bias * 100, current_rsi if current_rsi else 0))
    except Exception as e:
        log.warning("【首次运行】初始化震荡期状态异常: %s" % str(e))


# ==================== 退出震荡期检查 ====================
def check_and_exit_range_bound_mode(context):
    """检查是否需要退出震荡期"""
    if not g.enable_range_bound_mode or g.current_filter != '震荡期':
        return
    log.info("🔍 【震荡期退出检查】开始检测退出条件...")
    try:
        if g.benchmark_closes is None or len(g.benchmark_closes) < max(g.ma_period, g.lookback_high_low_days):
            log.warning("【震荡期退出检查】数据不足，跳过")
            return

        close = g.benchmark_closes
        high = g.benchmark_highs if g.benchmark_highs is not None else close
        low = g.benchmark_lows if g.benchmark_lows is not None else close

        current_price = close[-1]
        n = min(g.lookback_high_low_days, len(high))
        recent_high = np.max(high[-n:])
        recent_low = np.min(low[-n:])
        current_drawdown = (recent_high - current_price) / recent_high if recent_high > 0 else 0
        rise_from_low = (current_price - recent_low) / recent_low if recent_low > 0 else 0

        ma = np.mean(close[-g.ma_period:])
        current_rsi = calculate_rsi(close, period=14)

        log.info("📊 【震荡期数据】当前价: %.3f, 近%d日高点: %.3f, 低点: %.3f" % (
            current_price, g.lookback_high_low_days, recent_high, recent_low))
        log.info("📊 【震荡期数据】回撤: %.2f%%, 从低点涨幅: %.2f%%" % (
            current_drawdown * 100, rise_from_low * 100))

        recovery_signals = []
        if g.enable_low_point_rise_trigger and rise_from_low >= g.low_point_rise_threshold:
            recovery_signals.append("从低点上涨%.2f%%≥%.0f%%" % (
                rise_from_low * 100, g.low_point_rise_threshold * 100))

        if g.enable_stable_signal_trigger:
            if current_price > ma:
                recovery_signals.append("价格站上均线")
            if len(close) >= 2 and close[-1] > close[-2]:
                recovery_signals.append("价格回升")
            if g.previous_drawdown is not None and current_drawdown < g.previous_drawdown:
                recovery_signals.append("回撤收窄")
            if current_rsi is not None and g.previous_rsi is not None and current_rsi > g.previous_rsi:
                recovery_signals.append("RSI回升")
            drawdown_safe = current_drawdown < g.drawdown_recovery
            if drawdown_safe:
                g.stable_days += 1
            else:
                g.stable_days = 0

        g.previous_drawdown = current_drawdown
        g.previous_rsi = current_rsi

        # 震荡期天数
        range_bound_days = g.range_bound_days_count
        if range_bound_days >= g.max_range_bound_days:
            recovery_signals.append("震荡期满(%d天)" % range_bound_days)

        # 判断退出条件
        low_point_rise_ok = g.enable_low_point_rise_trigger and rise_from_low >= g.low_point_rise_threshold
        stable_signal_ok = False
        if g.enable_stable_signal_trigger:
            drawdown_safe = current_drawdown < g.drawdown_recovery
            stable_signal_ok = drawdown_safe and len(recovery_signals) >= 2 and g.stable_days >= 2
        force_exit = range_bound_days >= g.max_range_bound_days
        should_recover = low_point_rise_ok or stable_signal_ok or force_exit

        if should_recover:
            can_switch = True
            if g.last_switch_date is not None:
                days_since = _count_trading_days(g.last_switch_date, context.blotter.current_dt.date())
                if days_since < g.filter_switch_cooldown:
                    can_switch = False
                    log.info("⏳ 【震荡期退出】冷却期中，距上次切换 %d 交易日" % days_since)
            if can_switch:
                g.current_filter = '正常期'
                g.risk_state = '正常期'
                g.last_switch_date = context.blotter.current_dt.date()
                g.range_bound_start_date = None
                g.range_bound_days_count = 0
                g.stable_days = 0
                log.info("🔔 【退出震荡期】切换回拉普拉斯滤波器: %s" % '; '.join(recovery_signals))
        else:
            log.info("📌 【震荡期退出检查】未满足退出条件，保持震荡期(高斯)")
    except Exception as e:
        log.warning("【震荡期退出检查】判断出错: %s" % str(e))


# ==================== 进入震荡期检查 ====================
def check_and_enter_range_bound_mode(context):
    """检查是否需要进入震荡期"""
    if not g.enable_range_bound_mode:
        return
    log.info("🔍 【震荡期检查】开始检测进入条件...")

    can_switch = True
    if g.last_switch_date is not None:
        days_since = _count_trading_days(g.last_switch_date, context.blotter.current_dt.date())
        if days_since < g.filter_switch_cooldown:
            can_switch = False
            log.info("⏳ 【震荡期检查】冷却期中，距上次切换 %d 交易日" % days_since)

    if g.current_filter == '震荡期':
        log.info("📌 【震荡期检查】当前已在震荡期")
        return
    if not can_switch:
        return

    risk_signals = []
    try:
        if g.benchmark_closes is not None and len(g.benchmark_closes) >= max(g.ma_period, g.lookback_high_low_days):
            close = g.benchmark_closes
            current_price = close[-1]

            # 条件1: 乖离率过大
            if g.enable_bias_trigger:
                ma = np.mean(close[-g.ma_period:])
                bias = (current_price - ma) / ma if ma > 0 else 0
                if bias > g.bias_threshold:
                    risk_signals.append("乖离率过大(%.2f%%>%.0f%%)" % (
                        bias * 100, g.bias_threshold * 100))

            # 条件2: RSI超买回落
            if g.enable_rsi_trigger:
                current_rsi = calculate_rsi(close, period=14)
                if len(close) >= 15 and current_rsi is not None:
                    prev_rsi = calculate_rsi(close[:-1], period=14)
                    if prev_rsi is not None:
                        if prev_rsi > g.rsi_overbought and current_rsi < g.rsi_pullback and current_rsi < prev_rsi:
                            risk_signals.append("RSI超买回落(%.1f→%.1f)" % (prev_rsi, current_rsi))
    except Exception as e:
        log.warning("【震荡期检查】获取基准数据异常: %s" % str(e))

    # 条件3: 持仓触发止损
    if g.enable_stop_loss_trigger and g.stop_loss_triggered_today:
        risk_signals.append("今日触发止损")
        g.stop_loss_triggered_today = False

    if len(risk_signals) > 0:
        g.current_filter = '震荡期'
        g.risk_state = '震荡期'
        g.last_switch_date = context.blotter.current_dt.date()
        g.range_bound_start_date = _get_previous_trade_date(context)
        g.range_bound_days_count = 0
        g.stable_days = 0
        log.info("🔔 【进入震荡期】切换到高斯滤波器: %s" % '; '.join(risk_signals))
    else:
        log.info("✅ 【震荡期检查】未满足进入条件，保持正常期(拉普拉斯)")


# ==================== 动量得分计算 ====================
def calculate_and_log_ranked_etfs(context, data):
    """计算合并池中的标的动量得分"""
    if not g.merged_etf_pool:
        log.warning("【动量计算】合并池为空，无法计算")
        g.ranked_etfs_result = []
        return
    final_list = get_final_ranked_etfs(context, data)
    g.ranked_etfs_result = final_list


def calculate_momentum_score(price_series, lookback_days):
    """计算动量得分（加权线性回归）"""
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


def calculate_all_metrics_for_etf(etf, hist_closes, hist_volumes, current_price, today_vol, context):
    """计算单个标的所有动量指标"""
    try:
        etf_name = get_security_name(etf)
        price_series = np.append(hist_closes, current_price)
        min_len = max(g.lookback_days, g.short_momentum_lookback)
        if len(price_series) < min_len * 0.8:
            return None

        momentum_score, ann_ret, r_sq = calculate_momentum_score(price_series, g.lookback_days)
        if momentum_score is None:
            return None

        short_score, short_ret, short_r2 = calculate_momentum_score(price_series, g.short_momentum_lookback)
        passed_momentum = (g.min_score_threshold <= momentum_score <= g.max_score_threshold)
        passed_short = (g.short_momentum_min_score <= short_score <= g.short_momentum_max_score) if short_score is not None else False

        volume_ratio = get_volume_ratio(hist_volumes, today_vol, context)
        passed_loss = True
        day_ratios = []
        if len(price_series) >= 4:
            day1 = price_series[-1] / price_series[-2]
            day2 = price_series[-2] / price_series[-3]
            day3 = price_series[-3] / price_series[-4]
            day_ratios = [day1, day2, day3]
            if min(day_ratios) < g.loss:
                passed_loss = False

        premium_rate, passed_premium = None, True  # PTrade无NAV，始终通过

        # 滤波器计算
        laplace_value, laplace_slope, passed_laplace = 0, 0, False
        gaussian_value, gaussian_slope, passed_gaussian = 0, 0, False
        if len(price_series) >= 10:
            try:
                lvals = laplace_filter(price_series, s=g.laplace_s_param)
                if len(lvals) >= 2:
                    laplace_value = lvals[-1]
                    laplace_slope = lvals[-1] - lvals[-2]
                    passed_laplace = (current_price > lvals[-1] and laplace_slope > g.laplace_min_slope)
                g1, g2 = gaussian_filter_last_two(price_series, sigma=g.gaussian_sigma)
                gaussian_value = g1
                gaussian_slope = g1 - g2
                passed_gaussian = (current_price > g1 and gaussian_slope > g.gaussian_min_slope)
            except Exception:
                pass

        # 根据当前模式选择滤波器
        if g.current_filter == '正常期':
            filter_value, filter_slope, passed_filter = laplace_value, laplace_slope, passed_laplace
        else:
            filter_value, filter_slope, passed_filter = gaussian_value, gaussian_slope, passed_gaussian

        return {
            'etf': etf, 'etf_name': etf_name,
            'momentum_score': momentum_score, 'short_momentum_score': short_score,
            'annualized_returns': ann_ret, 'r_squared': r_sq,
            'current_price': current_price, 'volume_ratio': volume_ratio,
            'day_ratios': day_ratios, 'premium_rate': premium_rate,
            'passed_momentum': passed_momentum, 'passed_short_momentum': passed_short,
            'passed_r2': r_sq > g.r2_threshold if r_sq is not None else False,
            'passed_volume': volume_ratio is not None and volume_ratio < g.volume_threshold,
            'passed_loss': passed_loss, 'passed_premium': passed_premium,
            'laplace_value': laplace_value, 'laplace_slope': laplace_slope,
            'gaussian_value': gaussian_value, 'gaussian_slope': gaussian_slope,
            'passed_laplace': passed_laplace, 'passed_gaussian': passed_gaussian,
            'filter_value': filter_value, 'filter_slope': filter_slope,
            'passed_filter': passed_filter,
        }
    except Exception as e:
        etf_name = get_security_name(etf) if etf else etf
        log.warning("【指标计算】%s %s 计算失败: %s" % (etf, etf_name, str(e)))
        return None


def get_volume_ratio(hist_volumes, today_vol, context, lookback_days=None):
    """计算成交量比"""
    if lookback_days is None:
        lookback_days = g.volume_lookback
    try:
        if hist_volumes is None or len(hist_volumes) < lookback_days:
            return None
        past_n = hist_volumes[-lookback_days:]
        if np.any(np.isnan(past_n)) or np.any(past_n == 0):
            return None
        avg_volume = np.mean(past_n)
        if avg_volume == 0:
            return None
        now = context.blotter.current_dt
        elapsed_minutes = (now.hour - 9) * 60 + now.minute - 30
        if now.hour >= 13:
            elapsed_minutes -= 90
        elapsed_minutes = max(1, min(elapsed_minutes, 240))
        projected_today_vol = today_vol * (240.0 / elapsed_minutes)
        return projected_today_vol / avg_volume if avg_volume > 0 else 0
    except Exception:
        return None


# ==================== 滤波器函数 ====================
def gaussian_filter_last_two(price, sigma=1.2):
    """仅计算高斯滤波所需的最后两个点"""
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


def laplace_filter(price, s=0.05):
    """拉普拉斯滤波器"""
    alpha = 1 - np.exp(-s)
    L = np.zeros(len(price))
    L[0] = price[0]
    for t in range(1, len(price)):
        L[t] = alpha * price[t] + (1 - alpha) * L[t - 1]
    return L


def calculate_rsi(close, period=14):
    """计算RSI值"""
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
    except Exception:
        return None


# ==================== 过滤条件应用 ====================
def apply_filters(metrics_list):
    """根据开关应用所有过滤条件"""
    use_short = g.use_short_momentum_period
    steps = [
        ('动量得分', lambda m: m['passed_momentum'], not use_short),
        ('短期动量', lambda m: m['passed_short_momentum'], use_short),
        ('R²', lambda m: m['passed_r2'], g.enable_r2_filter),
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
                log.info("【过滤条件】%s: 通过 %d/%d" % (name, after, before))
    return filtered


def get_final_ranked_etfs(context, data):
    """主筛选函数：4步选股"""
    all_metrics = []
    etf_set = list(g.merged_etf_pool)
    use_short = g.use_short_momentum_period

    log.info("【动量得分计算】使用合并池，合计%d只ETF" % len(etf_set))
    log.info("【当前滤波器】%s" % ('拉普拉斯(正常期)' if g.current_filter == '正常期' else '高斯(震荡期)'))
    log.info("【动量模式】%s" % ('短期动量(21天,0-6分)' if use_short else '动量(25天,0-5分)'))

    for etf in etf_set:
        # 停牌检查
        try:
            status = get_stock_status(etf, 'HALT')
            if status:
                continue
        except Exception:
            pass

        if etf not in g.hist_closes:
            continue
        hist_closes = g.hist_closes[etf]
        hist_volumes = g.hist_volumes.get(etf, None)

        if len(hist_closes) < max(g.lookback_days, g.short_momentum_lookback):
            continue

        current_price = data[etf].price if etf in data else 0
        if current_price <= 0:
            continue

        # 当日累计成交量
        today_vol = data[etf].volume if etf in data else 0

        metrics = calculate_all_metrics_for_etf(etf, hist_closes, hist_volumes, current_price, today_vol, context)
        if metrics:
            if metrics['etf'] not in {m['etf'] for m in all_metrics}:
                all_metrics.append(metrics)

    # NaN处理
    for item in all_metrics:
        score = item.get('momentum_score')
        if score is None or (isinstance(score, float) and np.isnan(score)):
            item['momentum_score'] = float('-inf')
        ss = item.get('short_momentum_score')
        if ss is None or (isinstance(ss, float) and np.isnan(ss)):
            item['short_momentum_score'] = float('-inf')

    # 排序
    score_key = 'short_momentum_score' if use_short else 'momentum_score'
    all_metrics.sort(key=lambda x: x.get(score_key, float('-inf')), reverse=True)

    # >>> 第一步：全池排名 <<<
    log.info("")
    log.info(">>> 第一步：所有ETF按%s动量得分排序 <<<" % ('短期' if use_short else ''))
    for m in all_metrics[:100]:
        _log_metrics_line(m, use_short)

    # >>> 第二步：过滤后排名 <<<
    filtered_list = apply_filters(all_metrics)
    filtered_list.sort(key=lambda x: x.get(score_key, float('-inf')), reverse=True)
    top_10 = filtered_list[:10]

    log.info("")
    log.info(">>> 第二步：符合全部过滤条件的ETF(前10名) <<<")
    if top_10:
        for m in top_10:
            _log_metrics_line(m, use_short)
    else:
        log.info("（无符合条件的标的）")
        return []

    # >>> 第三步：候选池 <<<
    if len(top_10) >= g.holdings_num:
        ref_score = top_10[g.holdings_num - 1].get(score_key, float('-inf'))
        score_threshold = ref_score * g.score_threshold_ratio
        log.info("")
        log.info(">>> 第三步：得分≥第%d名得分%.4f×%.1f=%.4f的标的 <<<" % (
            g.holdings_num, ref_score, g.score_threshold_ratio, score_threshold))
        candidate_pool = [item for item in top_10 if item.get(score_key, float('-inf')) >= score_threshold]
    else:
        log.info("")
        log.info(">>> 第三步：前10名不足%d只，全部作为候选池 <<<" % g.holdings_num)
        candidate_pool = top_10[:]

    log.info("【候选池】共%d只标的：" % len(candidate_pool))
    for i, item in enumerate(candidate_pool):
        log.info("  %d. %s(%s) %s: %.4f" % (
            i + 1, item['etf_name'], item['etf'], score_key, item.get(score_key, 0)))

    # >>> 第四步：结合持仓调整 <<<
    log.info("")
    log.info(">>> 第四步：结合当前持仓进行调整 <<<")
    current_holdings = [code for code, pos in context.portfolio.positions.items() if pos.amount > 0]
    log.info("当前持仓标的：%s" % str(current_holdings))

    candidate_dict = {item['etf']: item for item in candidate_pool}
    retained = [candidate_dict[etf] for etf in current_holdings if etf in candidate_dict]
    log.info("其中存在于候选池中的持仓标的：%s" % str([item['etf'] for item in retained]))

    if len(retained) >= g.holdings_num:
        retained_sorted = sorted(retained, key=lambda x: x.get(score_key, float('-inf')), reverse=True)
        final_result = retained_sorted[:g.holdings_num]
    else:
        need = g.holdings_num - len(retained)
        remaining_pool = [item for item in candidate_pool if item['etf'] not in {r['etf'] for r in retained}]
        additional = remaining_pool[:need]
        final_result = retained + additional

    log.info("【最终目标】共%d只标的：" % len(final_result))
    for i, item in enumerate(final_result):
        log.info("  %d. %s(%s)" % (i + 1, item['etf_name'], item['etf']))
    log.info("=" * 50)
    return final_result


def _log_metrics_line(m, use_short):
    """输出单个标的的指标行"""
    def fmt(val, passed):
        return "%s %s" % (val, '✅' if passed else '❌')

    score_str = "%.4f" % m['momentum_score'] if m['momentum_score'] != float('-inf') else "nan"
    ss_str = "%.4f" % m['short_momentum_score'] if m['short_momentum_score'] != float('-inf') else "nan"
    r2_str = "%.3f" % m['r_squared'] if m['r_squared'] is not None and not (isinstance(m['r_squared'], float) and np.isnan(m['r_squared'])) else "nan"
    vol_str = "%.2f" % m['volume_ratio'] if m['volume_ratio'] is not None else "N/A"
    min_ratio = min(m['day_ratios']) if m['day_ratios'] else 'N/A'
    loss_str = "%.4f" % min_ratio if isinstance(min_ratio, float) else str(min_ratio)
    premium_str = "%.2f%%" % m['premium_rate'] if m['premium_rate'] is not None else "N/A"

    log.info("%s %s: 动量得分: %s，短期动量: %s，R²: %s，成交量比值: %s，短期风控: %s，溢价率: %s，拉普拉斯斜率: %.4f %s，高斯斜率: %.4f %s" % (
        m['etf'], m['etf_name'],
        fmt(score_str, m['passed_momentum']),
        fmt(ss_str, m['passed_short_momentum']),
        fmt(r2_str, m['passed_r2']),
        fmt(vol_str, m['passed_volume']),
        fmt(loss_str, m['passed_loss']),
        fmt(premium_str, m['passed_premium']),
        m['laplace_slope'], '✅' if m['passed_laplace'] else '❌',
        m['gaussian_slope'], '✅' if m['passed_gaussian'] else '❌',
    ))


# ==================== 交易执行 ====================
def execute_sell_trades(context, data):
    """卖出交易逻辑"""
    log.info("========== 卖出操作开始 ==========")
    ranked_etfs = getattr(g, 'ranked_etfs_result', [])
    target_etfs = []

    if ranked_etfs:
        for metrics in ranked_etfs[:g.holdings_num]:
            target_etfs.append(metrics['etf'])
            log.info("确定最终目标: %s %s" % (metrics['etf'], metrics['etf_name']))
    else:
        if check_defensive_etf_available(context, data):
            target_etfs = [g.defensive_etf]
            name = get_security_name(g.defensive_etf)
            log.info("🛡️ 确定最终目标(防御模式): %s %s" % (g.defensive_etf, name))
        else:
            log.info("💤 无最终目标(空仓模式)")
            target_etfs = []

    g.target_etfs_list = target_etfs
    target_set = set(target_etfs)
    sell_count = 0

    for code, pos in list(context.portfolio.positions.items()):
        if pos.amount > 0 and code not in target_set:
            name = get_security_name(code)
            if safe_sell(code, context):
                sell_count += 1
                log.info("✅ 已成功卖出: %s %s" % (code, name))

    log.info("本次共卖出%d只" % sell_count)
    log.info("========== 卖出操作完成 ==========")


def execute_buy_trades(context, data):
    """买入交易逻辑"""
    log.info("========== 买入操作开始 ==========")
    target_etfs = g.target_etfs_list
    if not target_etfs:
        log.info("今日无目标标的，保持空仓")
        log.info("========== 买入操作完成 ==========")
        return

    current_positions = set(code for code, pos in context.portfolio.positions.items() if pos.amount > 0)
    etfs_to_buy = [etf for etf in target_etfs if etf not in current_positions]
    actual_holding_count = len(current_positions)
    max_buy_count = max(0, g.holdings_num - actual_holding_count)
    num_to_buy = min(len(etfs_to_buy), max_buy_count)

    if num_to_buy <= 0:
        log.info("当前持仓(%d)已达目标(%d)，无需买入" % (actual_holding_count, g.holdings_num))
        log.info("========== 买入操作完成 ==========")
        return

    etfs_to_buy = etfs_to_buy[:num_to_buy]
    available_cash = context.portfolio.cash
    allocated_per_etf = available_cash // num_to_buy

    log.info("当前持仓: %d只, 目标: %d只, 本次买入: %d只" % (
        actual_holding_count, g.holdings_num, num_to_buy))
    log.info("可用现金: %.2f, 每只分配: %.2f" % (available_cash, allocated_per_etf))

    if allocated_per_etf < g.min_money:
        log.info("单只分配金额%.2f小于最小交易额%.2f，无法买入" % (allocated_per_etf, g.min_money))
        log.info("========== 买入操作完成 ==========")
        return

    for i, etf in enumerate(etfs_to_buy):
        target_value = allocated_per_etf
        if i == len(etfs_to_buy) - 1 and context.portfolio.cash >= g.min_money:
            target_value = context.portfolio.cash  # 最后一只用剩余全部现金

        if safe_buy_value(etf, target_value, context, data):
            log.info("✅ %s 下单成功" % etf)
        else:
            log.info("❌ %s 下单失败" % etf)

    log.info("========== 买入操作完成 ==========")


# ==================== 拆单买卖 ====================
def safe_sell(stock, context, max_shares=None):
    """分批卖出，每笔最大90万股，100股整手"""
    if max_shares is None:
        max_shares = g.max_order_shares
    pos = context.portfolio.positions.get(stock)
    if not pos:
        return False
    # 停牌检查
    try:
        status = get_stock_status(stock, 'HALT')
        if status:
            log.info("【卖出】%s 今日停牌，跳过" % stock)
            return False
    except Exception:
        pass
    # 涨跌停检查
    try:
        limit_info = check_limit(stock)
        if limit_info and stock in limit_info:
            if limit_info[stock] == -1:
                log.info("【卖出】%s 当前跌停，无法卖出" % stock)
                return False
    except Exception:
        pass
    # T+1守卫：使用enable_amount
    enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
    if enable_amount <= 0:
        log.info("【卖出】%s 无可卖数量(T+1)" % stock)
        return False

    name = get_security_name(stock)
    remaining = int(enable_amount)
    total_sold = 0
    while remaining > 0:
        batch = min(remaining, max_shares)
        batch = int(batch / 100) * 100
        if batch > 0:
            try:
                order(stock, -batch)
                total_sold += batch
                remaining -= batch
            except Exception as e:
                log.warning("【卖出】%s 拆单异常: %s" % (stock, str(e)))
                break
        else:
            # 剩余不足100股，无法按整手卖出，跳过零股
            if remaining > 0:
                log.info("【卖出】%s 剩余%d股不足100整手，放弃" % (stock, remaining))
            break

    if total_sold > 0:
        log.info("📤 卖出%s %s，数量: %d" % (stock, name, total_sold))
        return True
    return False


def safe_buy_value(stock, target_value, context, data, max_shares=None):
    """分批买入，按股数拆单（对齐聚宽 smart_order_target_value）"""
    if max_shares is None:
        max_shares = g.max_order_shares
    price = data[stock].price if stock in data else 0
    if price <= 0:
        log.info("【买入】%s 价格异常" % stock)
        return False

    # 停牌/涨跌停检查
    try:
        status = get_stock_status(stock, 'HALT')
        if status:
            log.info("【买入】%s 今日停牌" % stock)
            return False
    except Exception:
        pass

    try:
        limit_info = check_limit(stock)
        if limit_info and stock in limit_info:
            if limit_info[stock] == 1:
                log.info("【买入】%s 当前涨停" % stock)
                return False
            elif limit_info[stock] == -1:
                log.info("【买入】%s 当前跌停" % stock)
                return False
    except Exception:
        pass

    name = get_security_name(stock)
    # 计算目标总股数，向下取整到100股整手
    target_shares = int(target_value / price)
    target_shares = (target_shares // 100) * 100
    if target_shares <= 0 and target_value > 0:
        target_shares = 100
    if target_shares <= 0:
        return False

    # 检查最小交易额
    trade_value = target_shares * price
    if trade_value < g.min_money:
        log.info("【买入】%s %s 交易金额%.2f小于最小交易额%.2f，跳过" % (
            stock, name, trade_value, g.min_money))
        return False

    # 减去已有持仓量（如已持有该标的）
    current_pos = context.portfolio.positions.get(stock)
    current_amount = current_pos.amount if current_pos else 0
    amount_diff = target_shares - current_amount
    if amount_diff <= 0:
        log.info("【买入】%s %s 已持仓%d股，无需加仓" % (stock, name, current_amount))
        return False

    # 现金充足性检查：限制实际买入不超过可承受股数
    max_affordable = int(context.portfolio.cash / price / 100) * 100
    amount_diff = min(amount_diff, max_affordable)
    if amount_diff <= 0:
        log.info("【买入】%s %s 现金不足，无法买入" % (stock, name))
        return False

    # 按max_shares拆单买入
    remaining = amount_diff
    total_ordered = 0
    while remaining > 0:
        batch = min(remaining, max_shares)
        batch = (batch // 100) * 100
        if batch > 0:
            try:
                order(stock, batch)
                total_ordered += batch
                remaining -= batch
            except Exception as e:
                log.warning("【买入】%s 拆单异常: %s" % (stock, str(e)))
                break
        else:
            break

    if total_ordered > 0:
        est_value = total_ordered * price
        log.info("📦 买入%s %s，%d股，价格: %.3f，金额: %.2f" % (
            stock, name, total_ordered, price, est_value))
        return True
    return False


# ==================== 止损函数 ====================
def minute_level_stop_loss(context, data):
    """分钟级固定比例止损"""
    for code, pos in list(context.portfolio.positions.items()):
        enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
        if pos.amount <= 0 or enable_amount <= 0:
            continue
        current_price = data[code].price if code in data else 0
        if current_price <= 0:
            continue
        cost_price = pos.avg_cost
        if cost_price <= 0:
            continue
        if current_price <= cost_price * g.fixedStopLossThreshold:
            name = get_security_name(code)
            loss_pct = (current_price / cost_price - 1) * 100
            log.info("🚨 【分钟级固定止损】%s %s 触发止损，亏损: %.2f%%" % (code, name, loss_pct))
            if safe_sell(code, context):
                if g.enable_stop_loss_trigger:
                    g.stop_loss_triggered_today = True
                    log.info("✅ 【止损触发】记录今日止损，将在13:10检查并进入震荡期")


def minute_level_pct_stop_loss(context, data):
    """分钟级当日跌幅止损"""
    current_date = context.blotter.current_dt.date()
    if g.cache_date != current_date:
        g.yesterday_close_cache = dict(g.yesterday_close_map)
        g.cache_date = current_date

    for code, pos in list(context.portfolio.positions.items()):
        enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
        if pos.amount <= 0 or enable_amount <= 0:
            continue

        yesterday_close = g.yesterday_close_cache.get(code)
        if yesterday_close is None or yesterday_close <= 0:
            continue

        current_price = data[code].price if code in data else 0
        if current_price <= 0:
            continue

        stop_price = yesterday_close * g.pct_stop_loss_threshold
        if current_price <= stop_price:
            name = get_security_name(code)
            daily_loss = (current_price / yesterday_close - 1) * 100
            log.info("🚨 【分钟级跌幅止损】%s %s 触发止损，当日跌幅: %.2f%%" % (code, name, daily_loss))
            if safe_sell(code, context):
                if g.enable_stop_loss_trigger:
                    g.stop_loss_triggered_today = True
                    log.info("✅ 【止损触发】记录今日止损")


# ==================== 辅助函数 ====================
def _count_trading_days(start_date, end_date):
    """计算两个日期之间的交易日数（对齐聚宽get_trade_days）"""
    try:
        days = get_trade_days(start_date=start_date, end_date=end_date)
        if days is not None and len(days) > 0:
            return len(days) - 1  # 减去起始日本身
        return 0
    except Exception:
        # fallback: 日历日近似（交易日≈日历日×5/7）
        calendar_days = (end_date - start_date).days
        return max(0, int(calendar_days * 5 / 7))


def _get_previous_trade_date(context):
    """获取前一交易日（对齐聚宽context.previous_date）"""
    try:
        today = context.blotter.current_dt.date()
        days = get_trade_days(end_date=today, count=2)
        if days is not None and len(days) >= 2:
            return days[-2]  # 前一个交易日
        return today  # fallback
    except Exception:
        return context.blotter.current_dt.date()


def get_security_name(code):
    """安全获取证券名称（带缓存）"""
    if code in g.name_cache:
        return g.name_cache[code]
    try:
        name = get_stock_name(code)
        if name:
            g.name_cache[code] = name
            return name
    except Exception:
        pass
    return code


def check_defensive_etf_available(context, data):
    """检查防御性标的是否可交易"""
    etf = g.defensive_etf
    try:
        status = get_stock_status(etf, 'HALT')
        if status:
            log.info("防御性标的 %s 今日停牌" % etf)
            return False
    except Exception:
        pass

    try:
        limit_info = check_limit(etf)
        if limit_info and etf in limit_info:
            if limit_info[etf] == 1:
                log.info("防御性标的 %s 当前涨停" % etf)
                return False
            elif limit_info[etf] == -1:
                log.info("防御性标的 %s 当前跌停" % etf)
                return False
    except Exception:
        pass

    return True
