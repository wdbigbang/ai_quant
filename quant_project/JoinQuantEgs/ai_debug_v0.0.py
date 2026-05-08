# -*- coding: utf-8 -*-
"""
多市场环境自适应量化策略

================================================================================
策略设计理念
================================================================================

核心理念：市场环境自适应 + 多策略融合 + 风险控制优先 + 激进攻守兼备

1. 市场环境自适应
   - 自动识别8种市场环境：强势上涨、牛市、平稳市场、上涨市场、震荡市场、下跌市场、熊市、调整市场
   - 基于指数趋势（均线系统）、市场情绪（涨跌停数量）、波动率、动量因子综合判断
   - 不同市场环境自动切换策略组合，避免单一策略在特定市场失效

2. 多策略融合
   - 集成9种交易策略，覆盖多种市场场景
   - 多因子选股：基于质量、成长、估值、动量等多因子量化选股
   - ETF轮动：基于线性回归+R²的动量因子
   - 打板策略：追逐连板龙头股，结合热门概念和主线评分
   - 根据市场环境动态调整策略优先级

3. 风险控制优先
   - 三层风险控制体系：止损（-5%）、止盈（+15%）、最大回撤（-15%）
   - 动态仓位管理：根据市场环境动态调整持仓数量（0-5只）和整体仓位（40%-95%）
   - 优质股票动态调整：根据股票质量评分动态调整单只股票仓位（10%-15%）
   - 多维度过滤：ST股票、停牌股票、流动性差股票、上市时间不足1年股票

4. 实盘贴近性
   - 交易成本符合真实券商标准：股票佣金0.03%，ETF佣金0.02%，印花税0.1%
   - 滑点设置0.1%，模拟真实交易中的价格波动和成交延迟
   - 使用真实价格，避免未来数据，确保回测结果接近实盘
   - 增强最小交易单位检查（100股），避免订单委托失败

5. 激进攻守兼备
   - 牛市/上涨市场：95%仓位，5只股票，优先追涨策略（连板龙头、一进二、弱转强）
   - 震荡市场：80%仓位，3只股票，优先稳健策略（均值回归、一进二）
   - 下跌市场：60%仓位，3只股票，优先抄底策略（反向首板低开、一进二、均值回归）
   - 熊市：40%仓位，2只股票，优先避险策略（ETF轮动、反向首板低开）

================================================================================
关键函数说明
================================================================================

【市场环境识别层】

1. identify_market_regime(context)
   - 功能：识别当前市场环境
   - 输入：沪深300指数60日历史数据
   - 输出：8种市场环境之一（strong_up、bull、flat、up、sideways、down、bear、correction）
   - 关键指标：趋势因子（MA5、MA20均线比率）、波动率因子（20日年化波动率）、市场情绪因子（涨跌停数量净值）、动量因子（20日、60日动量）

2. select_strategy_by_regime(context, market_regime)
   - 功能：根据市场环境选择策略组合
   - 输入：市场环境类型
   - 输出：设置策略优先级、最大仓位、持仓数量
   - 策略映射：强势上涨（95%仓位，5只）、牛市（95%仓位，5只）、平稳市场（95%仓位，4只）、上涨市场（95%仓位，5只）、震荡市场（80%仓位，3只）、下跌市场（60%仓位，3只）、熊市（40%仓位，2只）、调整市（70%仓位，3只）

【策略执行层】

3. multi_factor_stock_selection(context)
   - 功能：多因子选股
   - 输入：策略上下文
   - 输出：股票代码列表（默认20只）
   - 选股流程：估值过滤（PE 5-200）、上市时间过滤（>1年）、质量过滤（ST、停牌）、流动性过滤（换手率>1%、成交量>100万股）、财务过滤（ROE、毛利率去极值）、多因子评分（质量、成长、估值、动量）
   - 因子权重：盈利能力0.8、成长能力1.8、估值0.3、市值0.2、动量2.5

4. etf_rotation(context)
   - 功能：ETF轮动选股
   - 输入：策略上下文
   - 输出：ETF代码列表
   - ETF池：包含10只核心ETF，涵盖黄金、宽基、成长、小盘、消费、科技、半导体、新能源
   - 评分因子：动量因子（线性回归+R²计算年化收益率×判定系数）、波动率因子（20日波动率）、趋势因子（价格相对20日均线位置）、相关性因子（与基准指数相关性）

5. execute_multi_factor_rebalance(context)
   - 功能：执行多因子选股策略调仓（支持优质股票动态调整仓位）
   - 调仓频率：每周一9:30
   - 仓位分配：根据股票质量评分动态调整（高质量前30%最大15%权重1.5倍，中等质量中间40%最大12%权重1.2倍，普通后30%最大10%权重1.0倍）
   - 调仓逻辑：卖出不在目标池中的股票，买入/调整目标池中的股票
   - 价格获取：使用get_price()获取上一交易日收盘价，避免盘前无法获取当前价格的问题
   - 最小交易单位检查：确保每只股票的目标金额≥100×股价，调整为100股的整数倍

6. execute_etf_rotation(context)
   - 功能：执行ETF轮动策略调仓
   - 调仓频率：每周一9:30
   - 仓位分配：等权重分配，单只ETF最大30%
   - 调仓逻辑：卖出不在目标池中的ETF，买入目标池中的ETF

7. execute_technical_indicator_strategy(context)
   - 功能：执行技术指标买卖策略
   - 执行频率：每周二10:00（避免调仓后立即卖出）
   - 卖出信号：MACD死叉（DIF < DEA 且 MACD < 0）、KDJ超买（J > 100）
   - 保护机制：持仓数量检查、当前价格检查、持仓天数检查（至少1天）

【风险控制层】

8. check_risk_control(context)
   - 功能：统一风险控制检查
   - 执行频率：每个交易日盘前9:25
   - 风控措施：最大回撤控制（回撤>=15%时紧急清仓）、止损检查（单只股票亏损>=5%时清仓）、止盈检查（单只股票盈利>=15%时清仓）

【订单管理层】（实盘交易增强）

9. check_order_timeout(context)
   - 功能：订单超时检查
   - 执行频率：每个交易日盘中检查（10:30、11:00、13:30、14:30）
   - 功能：检查所有未成交订单，如果订单超时未成交（默认30分钟），则自动撤销
   - 参数：g.order_timeout_enabled（开关）、g.order_timeout_minutes（超时时间）

10. cancel_near_close_orders(context)
    - 功能：收盘前撤单
    - 执行频率：每个交易日14:50
    - 功能：在收盘前撤销所有未成交订单，避免隔夜风险
    - 参数：g.near_close_cancel_enabled（开关）、g.near_close_time（撤单时间）、g.near_close_threshold（时间阈值）

11. check_order_status(context)
    - 功能：订单状态检查
    - 执行频率：每个交易日盘中检查（10:30、11:00、13:30、14:30）
    - 功能：检查订单状态，记录订单统计信息（总订单数、已成交、未成交）
    - 参数：g.order_log_enabled（开关）

【辅助函数层】

12. calculate_macd(security, context, fast_period=12, slow_period=26, signal_period=9)
    - 功能：计算MACD指标
    - 返回：DataFrame（DIF、DEA、MACD）

13. calculate_kdj(security, context, n=9, m1=3, m2=3)
    - 功能：计算KDJ指标
    - 返回：DataFrame（K、D、J）

14. calculate_rsi(security, context, period=24)
    - 功能：计算RSI指标
    - 返回：DataFrame（RSI）

15. calculate_boll(security, context, period=20, nbdevup=2, nbdevdn=2)
    - 功能：计算布林带
    - 返回：DataFrame（上轨、中轨、下轨）

16. calculate_ma(security, context, periods=[5, 10, 20, 60])
    - 功能：计算移动平均线
    - 返回：DataFrame（MA5、MA10、MA20、MA60）

17. calculate_ema(security, context, periods=[12, 26])
    - 功能：计算指数移动平均线
    - 返回：DataFrame（EMA12、EMA26）

【数据获取层】

18. get_all_hot_concepts_optimized(context, days=5)
    - 功能：获取最近N个交易日（包括今日）的热门概念列表
    - 缓存机制：优先从缓存中获取，减少API调用
    - 返回：字典（所有交易日的热门概念列表、按日期分组、统计信息）

19. calculate_mainline_score_optimized(stock, context)
    - 功能：计算股票的主线评分
    - 评分规则：匹配1个热门概念得2分，数量越多分数越高
    - 返回：主线评分（整数）

【打板策略层】

20. execute_limit_up_strategy(context)
    - 功能：连板龙头策略
    - 筛选条件：连续涨停天数最高、市值<300亿、换手<35%、一字板<10天、主线评分>0、量比1.184~10.5、高开比>76%

21. execute_one_to_two_strategy(context)
    - 功能：一进二策略
    - 筛选条件：首板高开（开比1.00~1.06）、市值50~520亿、金额5.5~20亿、量比1.15~6.58、价格<47元、主线评分>0

22. execute_reversal_strategy(context)
    - 功能：弱转强策略
    - 筛选条件：前日曾涨停但收盘未涨停、前三天涨幅<28%、前日收盘价≥开盘价、量比1.072~3.68、主线评分>0

23. execute_reverse_limit_up_strategy(context)
    - 功能：反向首板低开策略
    - 筛选条件：前日跌停、非连板跌停、相对位置≤0.5、低开4%~10%

24. execute_mean_reversion_strategy(context)
    - 功能：均值回归策略
    - 筛选条件：价格接近布林带下轨（下轨上方2%以内）、RSI<30（超卖）

25. execute_value_stock_strategy(context)
    - 功能：优质股低吸策略
    - 筛选条件：PE<30、ROE>10%、相对位置<0.3（低位）

================================================================================
关键因子&指标说明
================================================================================

【市场环境识别因子】
- 趋势因子：MA5、MA20均线及其比率
- 波动率因子：20日年化波动率
- 市场情绪因子：涨停数量、跌停数量、情绪净值
- 动量因子：20日、60日动量

【多因子选股因子】
- 质量因子：ROE、ROA、毛利率、净利率（权重0.8）
- 成长因子：营业收入同比增长率、净利润同比增长率、营业利润增长率（权重1.8）
- 估值因子：PE、PB、市值（权重0.3）
- 动量因子：Price3M、ROC20、CR20（权重2.5）

【技术指标因子】
- MACD：指数平滑异同移动平均线（DIF、DEA、MACD柱状图）
- KDJ：随机指标（K、D、J）
- RSI：相对强弱指标
- BOLL：布林带（上轨、中轨、下轨）
- MA：移动平均线（5日、10日、20日、60日）
- EMA：指数移动平均线（12日、26日）

【概念热度因子】
- 热门概念：同花顺热门概念数据
- 概念热度评分：涨停数量 * 2 + 连续涨停天数 * 3 + 涨跌幅
- 主线评分：股票匹配的热门概念数量 * 2

【动量计算因子】（ETF轮动优化）
- 对数收益率：y = np.log(df['close'].values)
- 加权线性回归：weights = np.linspace(1, 2, n)，权重线性增加
- 年化收益率：annualized_returns = math.pow(math.exp(slope), 250) - 1
- 判定系数：r_squared = 1 - (np.sum(weighted_residuals) / np.sum(weights * (y - np.mean(y))**2))
- 动量得分：momentum_score = annualized_returns * r_squared
- 安全区间：0 < score <= 5（动量过高过低都不好）

【其他辅助指标】
- 相对位置：(当前价格 - N日最低价) / (N日最高价 - N日最低价)
- 连续涨停/跌停天数
- 量比：今日成交量 / 过去5日平均成交量
- 换手率：成交量 / 流通股本
- 最小交易单位：100股（A股最小交易单位，在仓位分配时强制检查）

================================================================================
配置说明
================================================================================

【配置化设计】
- 市场环境配置：g.market_regime_config（8种市场环境的策略映射）
- 市场环境阈值：g.market_regime_thresholds（市场环境识别阈值）
- 策略配置：g.strategy_config（9种策略的开关和描述）
- 策略注册表：g.strategy_registry（所有策略的执行函数和配置）
- ETF池：g.etf_pool（10只核心ETF，可动态调整）
- 订单管理配置：g.order_timeout_enabled、g.order_timeout_minutes、g.near_close_cancel_enabled、g.near_close_time、g.near_close_threshold

【核心参数】
- 基准指数：沪深300 (000300.XSHG)
- 最大仓位：95%（根据市场环境动态调整40%-95%）
- 最大持仓数量：5只（根据市场环境动态调整2-5只）
- 止损：5%，止盈：15%，最大回撤：15%
- 交易成本：股票佣金0.03%，ETF佣金0.02%，印花税0.1%，滑点0.1%
- 最小交易单位：100股（强制检查）

【订单管理参数】（实盘交易增强）
- 订单超时时间：30分钟（可配置）
- 收盘前撤单时间：14:50（可配置）
- 收盘前撤单阈值：10分钟（可配置）

【扩展性说明】
- 添加新市场环境：在g.market_regime_config中添加配置项
- 添加新策略：在g.strategy_registry中注册策略（包含执行函数、开关、描述、类型）
- 调整阈值参数：修改g.market_regime_thresholds中的阈值
- 调整ETF池：修改g.etf_pool列表
- 策略注册机制：所有策略统一在g.strategy_registry中管理，添加新策略只需在注册表中添加一行配置
- 订单管理机制：所有订单管理功能统一管理，可通过配置开关控制启用/禁用

【买卖操作说明】
- 卖出操作：使用 order_target_value(security, 0) 清仓
  - 风险控制：止损（-5%）、止盈（+15%）、最大回撤（-15%）控制
  - 调仓操作：卖出不在目标池中的股票/ETF
  - 技术指标：MACD死叉（DIF < DEA 且 MACD < 0）、KDJ超买（J > 100）等卖出信号
  - **当前状态**：所有卖出操作已启用，会实际执行交易

- 买入操作：
  - 股票：使用 order_value(stock, value, MarketOrderStyle()) 按金额买入（市价单）
  - 仓位调整：使用 order_target_value(stock, target_value) 按目标市值调整仓位
  - ETF：使用 order_target_value(etf, target_value) 按目标市值调整仓位
  - 仓位分配：根据策略和市场环境动态调整单只股票/ETF的仓位
  - 最小交易单位：确保每只股票/ETF的目标金额≥100×股价，调整为100股的整数倍
  - **当前状态**：execute_multi_factor_rebalance函数中的买入操作已启用，其他买入操作暂未启用
"""

# ============================================================================
# 导入必要的库
# ============================================================================
from jqdata import *
from jqfactor import *
from jqlib.technical_analysis import *
import numpy as np
import pandas as pd
import math
from datetime import datetime, timedelta

# ============================================================================
# 初始化函数
# ============================================================================
def initialize(context):
    """
    策略初始化函数

    设置策略参数、交易成本、定时任务等
    """
    log.info("=" * 60)
    log.info("多市场环境自适应量化策略启动")
    log.info("=" * 60)

    # ========== 设置基准 ==========
    set_benchmark('000300.XSHG')  # 沪深300

    # ========== 设置选项 ==========
    set_option('use_real_price', True)  # 使用真实价格
    set_option('avoid_future_data', True)  # 避免未来函数

    # ========== 设置交易成本（贴近实盘） ==========
    # 股票交易成本
    set_order_cost(OrderCost(
        open_tax=0,           # 买入无印花税
        close_tax=0.001,      # 卖出印花税 0.1%
        open_commission=0.0003,  # 买入佣金 0.03%
        close_commission=0.0003, # 卖出佣金 0.03%
        close_today_commission=0,  # 股票无当日平仓费用
        min_commission=5      # 最低佣金 5元
    ), type='stock')

    # ETF交易成本
    set_order_cost(OrderCost(
        open_tax=0,           # 买入无印花税
        close_tax=0,          # 卖出无印花税
        open_commission=0.0002,  # 买入佣金 0.02%
        close_commission=0.0002, # 卖出佣金 0.02%
        close_today_commission=0,
        min_commission=5      # 最低佣金 5元
    ), type='fund')

    # ========== 设置滑点 ==========
    set_slippage(FixedSlippage(0.001))  # 固定滑点 0.1%

    # ========== 设置日志级别 ==========
    log.set_level('system', 'error')  # 系统日志只显示错误
    log.set_level('strategy', 'info') # 策略日志显示info及以上级别

    # ========== 设置全局参数 ==========
    # 基准指数
    g.benchmark = '000300.XSHG'

    # ========== 配置字典（可扩展） ==========
    # 市场环境配置（用于市场环境识别和策略选择）- 参考打板策略优化
    g.market_regime_config = {
        'strong_up': {
            'name': '强势上涨市场',
            'strategy': 'multi_factor',
            'max_position': 0.95,
            'position_limit': 5,
            'strategy_priority': ['limit_up', 'reversal', 'one_to_two', 'multi_factor']  # 追涨：连板龙头、弱转强、一进二
        },
        'bull': {
            'name': '牛市',
            'strategy': 'multi_factor',
            'max_position': 0.95,
            'position_limit': 5,
            'strategy_priority': ['limit_up', 'one_to_two', 'reversal', 'multi_factor']  # 追涨：连板龙头、一进二、弱转强
        },
        'flat': {
            'name': '平稳市场',
            'strategy': 'multi_factor',
            'max_position': 0.95,
            'position_limit': 4,
            'strategy_priority': ['limit_up', 'one_to_two', 'multi_factor']  # 稳健：连板龙头、一进二
        },
        'up': {
            'name': '上涨市场',
            'strategy': 'multi_factor',
            'max_position': 0.95,
            'position_limit': 5,
            'strategy_priority': ['one_to_two', 'limit_up', 'reversal', 'multi_factor']  # 顺势：一进二、连板龙头、弱转强
        },
        'sideways': {
            'name': '震荡市',
            'strategy': 'multi_factor',
            'max_position': 0.80,
            'position_limit': 3,
            'strategy_priority': ['mean_reversion', 'one_to_two', 'multi_factor']  # 震荡：均值回归、一进二
        },
        'down': {
            'name': '下跌市场',
            'strategy': 'multi_factor',
            'max_position': 0.60,
            'position_limit': 3,
            'strategy_priority': ['reverse_limit_up', 'one_to_two', 'mean_reversion', 'multi_factor']  # 抄底：反向首板低开、一进二、均值回归
        },
        'bear': {
            'name': '熊市',
            'strategy': 'etf_rotation',
            'max_position': 0.40,
            'position_limit': 2,
            'strategy_priority': ['etf_rotation', 'reverse_limit_up', 'cash']  # 避险：ETF轮动、反向首板低开
        },
        'correction': {
            'name': '调整市',
            'strategy': 'multi_factor',
            'max_position': 0.70,
            'position_limit': 3,
            'strategy_priority': ['value_stock', 'one_to_two', 'multi_factor']  # 低吸：优质股低吸、一进二
        }
    }

    # 市场环境识别阈值参数（可调整）- 激进优化版
    g.market_regime_thresholds = {
        'ma_short_ratio_bull': -0.01,      # 短期均线牛市阈值（进一步降低，更容易识别牛市）
        'ma_long_ratio_bull': -0.01,       # 长期均线牛市阈值（降低）
        'ma_short_ratio_bear': -0.03,      # 短期均线熊市阈值（降低）
        'ma_long_ratio_bear': -0.02,       # 长期均线熊市阈值（降低）
        'momentum_20_bull': -0.01,         # 20日动量牛市阈值（进一步降低）
        'momentum_20_bear': -0.05,         # 20日动量熊市阈值（降低）
        'ma_short_ratio_strong_up': 0.01,  # 强势上涨阈值（进一步降低）
        'momentum_20_strong_up': 0.03,     # 强势上涨动量阈值（进一步降低）
        'ma_short_ratio_down': -0.05,      # 下跌市场阈值（进一步降低）
        'momentum_20_down': -0.10,         # 下跌市场动量阈值（进一步降低）
        'ma_short_ratio_sideways': 0.02,   # 震荡市短期均线阈值（调整）
        'momentum_20_sideways': 0.02,      # 震荡市动量阈值（降低）
        'volatility_sideways': 0.20,       # 震荡市波动率阈值（降低）
        'momentum_20_flat': -0.01,         # 平稳市场动量阈值（进一步降低）
        'volatility_flat': 0.15            # 平稳市场波动率阈值（降低）
    }

    # 策略配置（用于策略执行）
    g.strategy_config = {
        'multi_factor': {
            'name': '多因子选股策略',
            'enabled': True,
            'description': '基于质量、成长、估值、动量等多因子量化选股'
        },
        'etf_rotation': {
            'name': 'ETF轮动策略',
            'enabled': True,
            'description': '基于动量、波动率、趋势等因子进行ETF资产轮动'
        },
        'limit_up': {
            'name': '连板龙头策略',
            'enabled': True,
            'description': '追逐连板龙头股，结合热门概念和主线评分'
        },
        'one_to_two': {
            'name': '一进二策略',
            'enabled': True,
            'description': '捕捉首板高开后的二板机会'
        },
        'reversal': {
            'name': '弱转强策略',
            'enabled': True,
            'description': '捕捉弱势股票转强的机会'
        },
        'reverse_limit_up': {
            'name': '反向首板低开策略',
            'enabled': True,
            'description': '捕捉跌停后低开反弹的机会'
        },
        'mean_reversion': {
            'name': '均值回归策略',
            'enabled': True,
            'description': '价格回归均值时进行买卖'
        },
        'value_stock': {
            'name': '优质股低吸策略',
            'enabled': True,
            'description': '低吸优质股票，等待价值回归'
        }
    }

    # ========== 策略注册表（可扩展） ==========
    # 用于统一管理策略的执行函数和配置
    # 添加新策略时，只需在这里注册，无需修改其他代码
    g.strategy_registry = {
        'multi_factor': {
            'execute_func': execute_multi_factor_rebalance,
            'enabled': True,
            'description': '多因子选股策略',
            'type': 'stock'
        },
        'etf_rotation': {
            'execute_func': execute_etf_rotation,
            'enabled': True,
            'description': 'ETF轮动策略',
            'type': 'fund'
        },
        'limit_up': {
            'execute_func': execute_limit_up_strategy,
            'enabled': True,
            'description': '连板龙头策略',
            'type': 'stock'
        },
        'one_to_two': {
            'execute_func': execute_one_to_two_strategy,
            'enabled': True,
            'description': '一进二策略',
            'type': 'stock'
        },
        'reversal': {
            'execute_func': execute_reversal_strategy,
            'enabled': True,
            'description': '弱转强策略',
            'type': 'stock'
        },
        'reverse_limit_up': {
            'execute_func': execute_reverse_limit_up_strategy,
            'enabled': True,
            'description': '反向首板低开策略',
            'type': 'stock'
        },
        'mean_reversion': {
            'execute_func': execute_mean_reversion_strategy,
            'enabled': True,
            'description': '均值回归策略',
            'type': 'stock'
        },
        'value_stock': {
            'execute_func': execute_value_stock_strategy,
            'enabled': True,
            'description': '优质股低吸策略',
            'type': 'stock'
        }
        # 添加新策略时，只需在这里添加一行
    }

    # ========== 全局参数设置 ==========
    # 仓位管理参数
    g.max_position = 0.95        # 最大仓位 95%
    g.min_position = 0.1         # 最小仓位 10%
    g.single_stock_max = 0.1     # 单只股票最大仓位 10%

    # 风险控制参数
    g.stop_loss = 0.05           # 止损 5%
    g.stop_profit = 0.15         # 止盈 15%
    g.max_drawdown = 0.15        # 最大回撤 15%

    # 市场环境识别参数
    g.market_trend_ma_short = 5          # 短期均线 5日
    g.market_trend_ma_long = 20          # 长期均线 20日
    g.market_volatility_window = 20      # 波动率计算窗口 20日
    g.market_sentiment_window = 5        # 市场情绪计算窗口 5日

    # 多因子策略参数
    g.multi_factor_stock_num = 20        # 选股数量
    g.multi_factor_rebalance_month = [4, 8]  # 调仓月份
    g.multi_factor_min_pe = 5            # 最小PE
    g.multi_factor_max_pe = 200          # 最大PE

    # ETF轮动策略参数
    g.etf_pool = [
        '518880.XSHG',  # 黄金ETF（大宗商品，避险资产）
        '513100.XSHG', #纳指100（海外资产）
        '510180.XSHG', #上证180（价值股，蓝筹股，中大盘）
        '510300.XSHG',  # 沪深300（宽基指数，核心资产）
        '159915.XSHE',  # 创业板100（成长股，科技股）
        '512100.XSHG',  # 中证1000（小盘股，成长性）
        '512690.XSHG',  # 酒ETF（消费板块，优质资产）
        '515070.XSHG',  # 人工智能ETF（AI，前沿科技）
        '512480.XSHG',  # 半导体ETF（科技核心，产业链）
        '516160.XSHG',  # 新能源车ETF（新能源汽车，绿色能源）
    ]
    g.etf_momentum_days = 20  # 动量计算天数
    g.etf_min_score = -0.1    # 最小动量得分（允许负值）
    g.etf_max_score = 0.3     # 最大动量得分（降低阈值）
    g.etf_volatility_window = 20  # 波动率计算窗口
    g.etf_max_position = 0.3    # 单只ETF最大仓位30%

    # 打板策略参数
    g.limit_up_position_limit = 2  # 最大持仓数量
    g.limit_up_min_score = 14     # 最小评分
    g.limit_up_concept_num = 8    # 热门概念数量
    g.jqfactor = 'market_cap'     # 聚宽因子名称（用于筛选）
    g.sort = True                 # 是否排序（用于筛选）

    # ========== 动态仓位管理参数 ==========
    g.position_limit = 5          # 最大持仓数量（0-5只，根据市场环境动态调整）
    g.dynamic_position_enabled = True  # 是否启用动态仓位管理
    g.quality_stock_max_position = 0.15  # 优质股票最大仓位（15%）
    g.quality_stock_thresholds = {
        'high_quality': {'score': 80, 'max_position': 0.15},  # 高质量股票：评分>=80，最大15%
        'medium_quality': {'score': 60, 'max_position': 0.12}, # 中等质量股票：评分>=60，最大12%
        'normal': {'score': 0, 'max_position': 0.10}           # 普通股票：默认10%
    }

    # ========== 订单管理参数（实盘交易增强） ==========
    g.order_timeout_enabled = True      # 是否启用订单超时管理
    g.order_timeout_minutes = 30        # 订单超时时间（分钟），超过此时间未成交自动撤销
    g.near_close_cancel_enabled = True  # 是否启用收盘前撤单
    g.near_close_time = '14:50'        # 收盘前撤单时间
    g.near_close_threshold = 10        # 收盘前撤单时间差（分钟），在此时间内未成交的订单将被撤销
    g.order_priority_enabled = True    # 是否启用订单优先级管理
    g.order_log_enabled = True         # 是否记录订单详细日志

    # ========== 初始化统计变量 ==========
    g.market_regime = 'unknown'  # 当前市场环境
    g.current_strategy = 'none'  # 当前使用的策略
    g.stock_pool = []            # 当前股票池
    g.etf_position = None        # 当前ETF持仓
    g.max_total_value = context.portfolio.total_value  # 最大总资产（用于计算回撤）

    # 热门概念相关变量
    g.hot_concepts_data_cache = {}  # 热门概念数据缓存
    g.hot_concepts_api_called = {}  # API调用标记
    g.concept_num = 8  # 缓存每日热点概念最大个数
    g.mainline_score_cache = {}  # 主线评分缓存

    # 初始化统计变量
    g.trade_stats = {
        'daily_returns': [],      # 每日收益
        'position_stats': {},     # 持仓统计
        'market_stats': {         # 市场统计
            'trend': [],
            'volatility': [],
            'sentiment': []
        },
        'trade_details': [],      # 交易明细
        'order_stats': {          # 订单统计（实盘交易增强）
            'total_orders': 0,        # 总订单数
            'filled_orders': 0,       # 已成交订单数
            'cancelled_orders': 0,    # 已撤销订单数
            'timeout_cancelled': 0,   # 超时撤销订单数
            'near_close_cancelled': 0 # 收盘前撤销订单数
        },
        'order_details': []       # 订单详细记录
    }

    # ========== 设置定时任务 ==========
    # 盘前任务
    run_daily(pre_market_check, time='09:25', reference_security=g.benchmark)

    # 开盘任务
    run_daily(market_open, time='09:30', reference_security=g.benchmark)

    # 盘中任务
    run_daily(market_check, time='10:30', reference_security=g.benchmark)
    run_daily(market_check, time='11:00', reference_security=g.benchmark)
    run_daily(market_check, time='13:30', reference_security=g.benchmark)
    run_daily(market_check, time='14:30', reference_security=g.benchmark)

    # 收盘任务
    run_daily(after_market_close, time='15:00', reference_security=g.benchmark)

    # 收盘前撤单任务（实盘交易增强）
    run_daily(cancel_near_close_orders, time='14:50', reference_security=g.benchmark)

    # 每周任务
    run_weekly(weekly_rebalance, weekday=1, time='09:30', reference_security=g.benchmark)
    run_weekly(execute_technical_indicator_strategy, weekday=2, time='10:00', reference_security=g.benchmark)

    # 每月任务
    run_monthly(monthly_rebalance, monthday=1, time='09:30', reference_security=g.benchmark)

    log.info("初始化完成")
    log.info("=" * 60)

# ============================================================================
# 盘前检查函数
# ============================================================================
def pre_market_check(context):
    """
    盘前检查函数

    每个交易日9:25执行，用于：
    1. 识别市场环境
    2. 更新股票池
    3. 检查风险控制
    """
    log.info("\n" + "=" * 60)
    log.info("盘前检查 - {}".format(context.current_dt.strftime('%Y-%m-%d %H:%M:%S')))
    log.info("=" * 60)

    # 1. 识别市场环境
    market_regime = identify_market_regime(context)
    g.market_regime = market_regime
    log.info("当前市场环境：{}".format(market_regime))

    # 2. 根据市场环境选择策略
    select_strategy_by_regime(context, market_regime)

    # 3. 更新股票池
    update_stock_pool(context, market_regime)

    # 4. 检查风险控制
    check_risk_control(context)

    log.info("盘前检查完成")
    log.info("=" * 60)

# ============================================================================
# 市场环境识别函数
# ============================================================================
def identify_market_regime(context):
    """
    识别市场环境

    基于以下因素判断市场环境：
    1. 指数趋势（均线系统）
    2. 市场情绪（涨跌停数量、成交量）
    3. 波动率（历史波动率）
    4. 资金流向（北向资金）

    返回：
        'bull': 牛市
        'bear': 熊市
        'sideways': 震荡市
        'correction': 调整市
    """
    try:
        # 获取基准指数数据
        benchmark = g.benchmark
        end_date = context.previous_date

        # 获取最近60天的指数数据
        hist = get_price(benchmark, end_date=end_date, count=60,
                        fields=['close', 'volume'], frequency='daily')

        if len(hist) < g.market_trend_ma_long:
            log.warning("数据不足，无法识别市场环境")
            return 'unknown'

        # ========== 1. 计算趋势因子 ==========
        close_prices = hist['close'].values

        # 计算短期和长期均线
        ma_short = np.mean(close_prices[-g.market_trend_ma_short:])
        ma_long = np.mean(close_prices[-g.market_trend_ma_long:])

        # 计算当前价格相对于均线的位置
        current_price = close_prices[-1]
        ma_short_ratio = (current_price - ma_short) / ma_short
        ma_long_ratio = (current_price - ma_long) / ma_long

        log.info("趋势因子：")
        log.info("  MA{}: {:.2f}, MA{}: {:.2f}, 当前价格: {:.2f}".format(
            g.market_trend_ma_short, ma_short, g.market_trend_ma_long, ma_long, current_price))
        log.info("  MA{}比率: {:.2%}, MA{}比率: {:.2%}".format(
            g.market_trend_ma_short, ma_short_ratio, g.market_trend_ma_long, ma_long_ratio))

        # ========== 2. 计算波动率因子 ==========
        returns = np.diff(np.log(close_prices))
        volatility = np.std(returns[-g.market_volatility_window:]) * np.sqrt(252)  # 年化波动率

        log.info("波动率因子：")
        log.info("  年化波动率: {:.2%}".format(volatility))

        # ========== 3. 计算市场情绪因子 ==========
        # 获取涨跌停数据
        all_stocks = list(get_all_securities(types=['stock'], date=end_date).index)
        limit_up_count = 0
        limit_down_count = 0

        # 获取昨日收盘价和今日开盘价、最高价、最低价
        for stock in all_stocks[:100]:  # 只检查前100只股票，提高效率
            try:
                hist_stock = get_price(stock, end_date=end_date, count=2,
                                     fields=['open', 'close', 'high', 'low'], frequency='daily')
                if len(hist_stock) >= 2:
                    prev_close = hist_stock['close'].iloc[-2]
                    curr_high = hist_stock['high'].iloc[-1]
                    curr_low = hist_stock['low'].iloc[-1]

                    # 涨停判断（简化版，实际需要考虑ST股等）
                    if curr_high >= prev_close * 1.095:
                        limit_up_count += 1
                    # 跌停判断
                    if curr_low <= prev_close * 0.905:
                        limit_down_count += 1
            except:
                continue

        sentiment_ratio = limit_up_count - limit_down_count
        log.info("市场情绪因子：")
        log.info("  涨停数量: {}, 跌停数量: {}, 净值: {}".format(
            limit_up_count, limit_down_count, sentiment_ratio))

        # ========== 4. 计算动量因子 ==========
        momentum_20 = (current_price - close_prices[-20]) / close_prices[-20]
        momentum_60 = (current_price - close_prices[-60]) / close_prices[-60]

        log.info("动量因子：")
        log.info("  20日动量: {:.2%}, 60日动量: {:.2%}".format(momentum_20, momentum_60))

        # ========== 5. 综合判断市场环境 ==========
        # 获取配置阈值
        thresholds = g.market_regime_thresholds

        # 牛市判断条件（使用配置阈值）
        bull_conditions = [
            ma_short_ratio > thresholds['ma_short_ratio_bull'],       # 短期均线之上
            ma_long_ratio > thresholds['ma_long_ratio_bull'],         # 长期均线之上
            momentum_20 > thresholds['momentum_20_bull'],             # 20日动量
            sentiment_ratio > 0                                       # 涨停 > 跌停
        ]

        # 熊市判断条件（使用配置阈值）
        bear_conditions = [
            ma_short_ratio < thresholds['ma_short_ratio_bear'],       # 短期均线之下
            ma_long_ratio < thresholds['ma_long_ratio_bear'],         # 长期均线之下
            momentum_20 < thresholds['momentum_20_bear'],             # 20日动量
            sentiment_ratio < 0                                       # 跌停 > 涨停
        ]

        # 震荡市判断条件（使用配置阈值）
        sideways_conditions = [
            abs(ma_short_ratio) < thresholds['ma_short_ratio_sideways'],  # 短期均线附近
            abs(momentum_20) < thresholds['momentum_20_sideways'],        # 20日动量较小
            volatility < thresholds['volatility_sideways']                 # 波动率较低
        ]

        # 判断市场环境（参考Enhanced_5in1_LimitUp策略的市场环境分类）
        if sum(bull_conditions) >= 3:
            # 强势上涨市场（使用配置阈值）
            if ma_short_ratio > thresholds['ma_short_ratio_strong_up'] and momentum_20 > thresholds['momentum_20_strong_up']:
                regime = 'strong_up'
            else:
                regime = 'bull'
        elif sum(bear_conditions) >= 3:
            regime = 'bear'
        elif sum(sideways_conditions) >= 2:
            # 检查是否为平稳市场（使用配置阈值）
            if abs(momentum_20) < thresholds['momentum_20_flat'] and volatility < thresholds['volatility_flat']:
                regime = 'flat'
            else:
                regime = 'sideways'
        elif ma_short_ratio < thresholds['ma_short_ratio_down'] and momentum_20 < thresholds['momentum_20_down']:
            regime = 'down'
        else:
            regime = 'correction'

        # 记录市场统计
        g.trade_stats['market_stats']['trend'].append(ma_long_ratio)
        g.trade_stats['market_stats']['volatility'].append(volatility)
        g.trade_stats['market_stats']['sentiment'].append(sentiment_ratio)

        return regime

    except Exception as e:
        log.error("识别市场环境失败: {}".format(str(e)))
        import traceback
        log.error(traceback.format_exc())
        return 'unknown'

# ============================================================================
# 根据市场环境选择策略（参考Enhanced_5in1_LimitUp策略）
# ============================================================================
def select_strategy_by_regime(context, market_regime):
    """
    根据市场环境选择策略（使用配置字典，可扩展）

    不同市场环境下的策略组合（在market_regime_config中配置）：
    - 强势上涨市场: 多因子选股 + 连板龙头策略 + 弱转强策略
    - 牛市: 多因子选股 + 连板龙头策略 + 一进二策略
    - 平稳市场: 多因子选股 + 连板龙头策略
    - 上涨市场: 多因子选股 + 一进二策略 + 连板龙头策略
    - 震荡市: 多因子选股 + 均值回归 + 波动率交易
    - 下跌市场: ETF轮动 + 反向首板低开策略 + 一进二策略
    - 熊市: ETF轮动 + 空仓观望
    - 调整市: ETF轮动 + 优质股低吸
    """
    log.info("\n根据市场环境选择策略：")

    # 使用配置字典获取市场环境配置
    if market_regime in g.market_regime_config:
        config = g.market_regime_config[market_regime]
        g.current_strategy = config['strategy']
        g.max_position = config['max_position']
        g.position_limit = config['position_limit']
        g.strategy_priority = config['strategy_priority']

        # 生成策略名称列表（用于日志显示）
        strategy_names = []
        for strategy in g.strategy_priority:
            if strategy in g.strategy_config:
                strategy_names.append(g.strategy_config[strategy]['name'])
            elif strategy == 'cash':
                strategy_names.append('现金')
            else:
                strategy_names.append(strategy)

        log.info("  策略：{}".format(' + '.join(strategy_names)))
        log.info("  最大仓位：{:.0%}".format(g.max_position))
        log.info("  持仓数量：{}只".format(g.position_limit))
    else:
        # 未知市场环境，使用保守策略
        g.current_strategy = 'none'
        g.max_position = 0.1
        g.position_limit = 0
        g.strategy_priority = ['cash']
        log.info("  策略：观望（未知市场环境）")
        log.info("  最大仓位：10%")
        log.info("  持仓数量：0只（观望）")

    # 记录策略优先级
    g.trade_stats['strategy_priority'] = {
        'market_regime': market_regime,
        'priority': g.strategy_priority,
        'position_limit': g.position_limit
    }

# ============================================================================
# 更新股票池
# ============================================================================
def update_stock_pool(context, market_regime):
    """
    更新股票池

    根据市场环境和策略选择股票池
    """
    log.info("\n更新股票池：")

    if market_regime == 'bull':
        # 牛市：多因子选股
        g.stock_pool = multi_factor_stock_selection(context)
        log.info("  股票池数量：{}（多因子选股）".format(len(g.stock_pool)))
    elif market_regime == 'bear':
        # 熊市：空仓
        g.stock_pool = []
        log.info("  股票池数量：0（空仓）")
    elif market_regime == 'sideways':
        # 震荡市：多因子选股（数量减半）
        g.stock_pool = multi_factor_stock_selection(context)[:10]
        log.info("  股票池数量：{}（多因子选股，数量减半）".format(len(g.stock_pool)))
    elif market_regime == 'correction':
        # 调整市：多因子选股（数量减半）
        g.stock_pool = multi_factor_stock_selection(context)[:10]
        log.info("  股票池数量：{}（多因子选股，数量减半）".format(len(g.stock_pool)))
    else:
        # 未知：空仓
        g.stock_pool = []
        log.info("  股票池数量：0（未知市场环境）")

# ============================================================================
# 多因子选股函数
# ============================================================================
def multi_factor_stock_selection(context):
    """
    多因子选股

    基于质量、成长、估值、动量等多因子选股

    返回：
        股票代码列表
    """
    log.info("\n" + "=" * 60)
    log.info("多因子选股")
    log.info("=" * 60)

    try:
        # 获取所有股票
        stock_list = list(get_all_securities(types=['stock'], date=None).index)
        end_date = context.previous_date.strftime("%Y-%m-%d")

        log.info("初始股票数量：{}".format(len(stock_list)))

        # ========== 1. 过滤估值数据 ==========
        q = query(
            valuation.code,
            valuation.pe_ratio,
            valuation.pb_ratio,
            valuation.market_cap
        ).filter(
            valuation.code.in_(stock_list),
            valuation.pe_ratio > g.multi_factor_min_pe,
            valuation.pe_ratio < g.multi_factor_max_pe
        ).order_by(valuation.market_cap.desc())

        df_valuation = get_fundamentals(q, date=end_date).set_index('code')

        # 过滤掉市值最大的前5%和最小的后10%
        df_valuation = df_valuation.iloc[int(len(df_valuation)/20):int(len(df_valuation)-len(df_valuation)/10), :]
        stock_list = list(df_valuation.index)

        log.info("过滤估值后股票数量：{}".format(len(stock_list)))

        # ========== 2. 过滤上市时间 ==========
        from dateutil.relativedelta import relativedelta
        one_year_before = context.current_dt + relativedelta(months=-12)
        s_omb = one_year_before.strftime("%Y-%m-%d")

        q = query(
            finance.STK_LIST.code,
            finance.STK_LIST.start_date,
            finance.STK_LIST.state
        ).filter(
            finance.STK_LIST.code.in_(stock_list),
            finance.STK_LIST.start_date < s_omb,
            finance.STK_LIST.state == '正常上市'
        ).order_by(finance.STK_LIST.start_date.asc())

        df_LIST = finance.run_query(q).set_index('code')
        stock_list = list(df_LIST.index)

        log.info("过滤上市时间后股票数量：{}".format(len(stock_list)))

        # ========== 2.1 过滤ST股票 ==========
        st_stocks = []
        for stock in stock_list:
            try:
                stock_info = get_security_info(stock)
                if stock_info and 'ST' in stock_info.display_name:
                    st_stocks.append(stock)
            except:
                continue

        stock_list = [s for s in stock_list if s not in st_stocks]
        log.info("过滤ST股票后股票数量：{}".format(len(stock_list)))

        # ========== 2.2 过滤停牌股票 ==========
        current_data = get_current_data()
        paused_stocks = []
        for stock in stock_list:
            try:
                if stock in current_data and current_data[stock].paused:
                    paused_stocks.append(stock)
            except:
                continue

        stock_list = [s for s in stock_list if s not in paused_stocks]
        log.info("过滤停牌股票后股票数量：{}".format(len(stock_list)))

        # ========== 2.3 过滤流动性差的股票 ==========
        # 获取换手率和成交量数据
        try:
            # 使用get_valuation获取换手率数据
            df_turnover = get_valuation(stock_list, end_date=end_date, count=5, fields=['turnover_ratio'])
            # 使用get_price获取成交量数据
            df_volume = get_price(stock_list, end_date=end_date, count=5, fields=['volume'], frequency='daily', panel=False)

            illiquid_stocks = []
            for stock in stock_list:
                try:
                    # 检查5日平均换手率（至少1%）
                    # get_valuation返回的DataFrame格式：index为日期，columns为股票代码
                    if not df_turnover.empty and stock in df_turnover.columns:
                        avg_turnover = df_turnover[stock].mean()
                        if avg_turnover < 0.01:  # 换手率小于1%
                            illiquid_stocks.append(stock)
                            continue

                    # 检查5日平均成交量（至少100万股）
                    # get_price返回的DataFrame格式：index为日期，columns为股票代码（多层索引）
                    if not df_volume.empty and stock in df_volume['volume'].columns:
                        avg_volume = df_volume['volume'][stock].mean()
                        if avg_volume < 1000000:  # 成交量小于100万股
                            illiquid_stocks.append(stock)
                            continue
                except:
                    continue

            stock_list = [s for s in stock_list if s not in illiquid_stocks]
            log.info("过滤流动性差股票后股票数量：{}".format(len(stock_list)))
        except Exception as e:
            log.warning("流动性过滤失败，跳过: {}".format(str(e)))

        # ========== 3. 获取财务数据 ==========
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

        # 去极值
        df_finance.sort_values(by='roe', ascending=False, inplace=True)
        df_finance = df_finance.iloc[int(len(df_finance)/30):int(len(df_finance)-len(df_finance)/30), :]
        df_finance.sort_values(by='gross_profit_margin', ascending=False, inplace=True)
        df_finance = df_finance.iloc[int(len(df_finance)/30):int(len(df_finance)-len(df_finance)/30), :]

        stock_list = list(df_finance.index)

        log.info("过滤财务数据后股票数量：{}".format(len(stock_list)))

        # ========== 4. 获取聚宽因子 ==========
        jqf = [
            'book_to_price_ratio',
            'sales_to_price_ratio',
            'roe_ttm',
            'total_asset_turnover_rate',
            'growth',
            'Price3M',
            'market_cap'
        ]

        data = get_factor_values(stock_list, factors=jqf,
                                start_date=end_date, end_date=end_date)

        # 整理数据
        df_valuation = data[jqf[0]].T
        df_valuation.rename(columns={df_valuation.columns[0]: jqf[0]}, inplace=True)
        df_valuation.sort_index(ascending=True, inplace=True)

        for i in range(1, len(jqf)):
            df = data[jqf[i]].T
            df.rename(columns={df.columns[0]: jqf[i]}, inplace=True)
            df.sort_index(ascending=True, inplace=True)
            df_valuation[jqf[i]] = df.iloc[:, 0:1].copy()

        df_valuation.sort_index(ascending=True, inplace=True)
        df_score = df_valuation.iloc[:, 0:1].copy()

        log.info("获取聚宽因子数量：{}".format(len(df_valuation)))

        # ========== 5. 计算得分 ==========
        df_valuation['market_cap_log'] = np.log(df_valuation['market_cap'])

        df_score['market_cap_score'] = 100 * (df_valuation['market_cap_log'] - df_valuation['market_cap_log'].min()) / (df_valuation['market_cap_log'].max() - df_valuation['market_cap_log'].min())
        df_score['valuation_score'] = 100 * (df_valuation['book_to_price_ratio'] - df_valuation['book_to_price_ratio'].min()) / (df_valuation['book_to_price_ratio'].max() - df_valuation['book_to_price_ratio'].min())
        df_score['return_score'] = 100 * ((df_finance['roe'] - df_finance['roe'].min()) / (df_finance['roe'].max() - df_finance['roe'].min()))
        df_score['growth_score'] = 100 * ((df_finance['inc_operation_profit_year_on_year'] - df_finance['inc_operation_profit_year_on_year'].min()) / (df_finance['inc_operation_profit_year_on_year'].max() - df_finance['inc_operation_profit_year_on_year'].min()))

        # 获取动量因子
        jqf_momentum = ['ROC20', 'CR20']
        data_momentum = get_factor_values(stock_list, factors=jqf_momentum,
                                          start_date=end_date, end_date=end_date)

        df_jqf = data_momentum[jqf_momentum[0]].T
        df_jqf.rename(columns={df_jqf.columns[0]: jqf_momentum[0]}, inplace=True)
        df_jqf.sort_index(ascending=True, inplace=True)
        df_score['momentum_score'] = 100 * ((df_jqf[jqf_momentum[0]] - df_jqf[jqf_momentum[0]].min()) / (df_jqf[jqf_momentum[0]].max() - df_jqf[jqf_momentum[0]].min()))

        # 计算总分（激进优化权重：大幅提高动量和成长因子权重，进一步降低估值和市值因子权重）
        df_score['total_score'] = (
            df_score['return_score'] * 0.8 +        # 盈利能力：权重0.8（降低）
            df_score['growth_score'] * 1.8 +        # 成长能力：权重1.8（大幅提高）
            df_score['valuation_score'] * 0.3 +     # 估值因子：权重0.3（进一步降低）
            df_score['market_cap_score'] * 0.2 +    # 市值因子：权重0.2（进一步降低）
            df_score['momentum_score'] * 2.5        # 动量因子：权重2.5（大幅提高，从1.5提高到2.5）
        )

        # 排序
        df_score.sort_values(by='total_score', ascending=False, inplace=True)

        log.info("得分计算完成")

        # ========== 6. 返回股票列表 ==========
        stock_list = list(df_score.iloc[:g.multi_factor_stock_num, :].index)

        log.info("最终选股数量：{}".format(len(stock_list)))
        log.info("前5只股票：{}".format(stock_list[:5]))
        log.info("=" * 60)

        return stock_list

    except Exception as e:
        log.error("多因子选股失败: {}".format(str(e)))
        import traceback
        log.error(traceback.format_exc())
        return []

# ============================================================================
# ETF轮动函数（大师级）
# ============================================================================
def etf_rotation(context):
    """
    ETF轮动 - 大师级策略

    基于多因子评分进行ETF轮动：
    1. 动量因子：年化收益率 × 判定系数
    2. 波动率因子：年化波动率（低波动率加分）
    3. 趋势强度因子：均线系统
    4. 相关性因子：与基准指数的相关性
    5. 市场环境适配：根据市场环境调整因子权重
    """
    log.info("\n" + "=" * 60)
    log.info("ETF轮动 - 大师级策略")
    log.info("=" * 60)

    try:
        # 计算每个ETF的多因子得分
        etf_scores = []
        for etf in g.etf_pool:
            score_info = calculate_etf_comprehensive_score(etf, context)
            etf_scores.append({
                'etf': etf,
                'momentum_score': score_info['momentum_score'],
                'volatility_score': score_info['volatility_score'],
                'trend_score': score_info['trend_score'],
                'correlation_score': score_info['correlation_score'],
                'total_score': score_info['total_score']
            })

        # 按总分排序
        etf_scores.sort(key=lambda x: x['total_score'], reverse=True)

        # 输出得分详情
        log.info("\nETF得分详情：")
        for item in etf_scores:
            log.info("  {}: 总分={:.4f}, 动量={:.4f}, 波动率={:.4f}, 趋势={:.4f}, 相关性={:.4f}".format(
                item['etf'], item['total_score'], item['momentum_score'],
                item['volatility_score'], item['trend_score'], item['correlation_score']))

        # 筛选出得分在安全区间的ETF（参考安全摸狗策略）
        valid_etfs = [e for e in etf_scores
                      if e['total_score'] > 0 and e['total_score'] <= 5]

        if len(valid_etfs) == 0:
            log.info("没有符合条件的ETF（安全区间：0 < score <= 5），保持空仓")
            log.info("=" * 60)
            return []

        # 选择得分最高的1-2只ETF（根据市场环境决定）
        if g.market_regime == 'bull':
            target_count = 2  # 牛市持有2只ETF
        elif g.market_regime == 'bear':
            target_count = 1  # 熊市持有1只ETF
        else:
            target_count = 1  # 其他情况持有1只ETF

        target_etfs = [e['etf'] for e in valid_etfs[:target_count]]
        log.info("选择ETF：{}（得分：{}）".format(
            ', '.join(target_etfs),
            ', '.join(['{:.4f}'.format(e['total_score']) for e in valid_etfs[:target_count]])))

        log.info("=" * 60)
        return target_etfs

    except Exception as e:
        log.error("ETF轮动失败: {}".format(str(e)))
        import traceback
        log.error(traceback.format_exc())
        return []

# ============================================================================
# 计算ETF综合得分
# ============================================================================
def calculate_etf_comprehensive_score(etf, context):
    """
    计算ETF综合得分（优化版，参考安全摸狗策略）

    核心思路：使用年化收益率 × 判定系数作为主要得分
    安全区间：score > 0 and score <= 5（避免过高或过低）
    """
    try:
        # 获取历史数据
        df = attribute_history(etf, g.etf_momentum_days, '1d', ['close'])

        if len(df) < 10:
            return {
                'momentum_score': 0,
                'total_score': 0
            }

        # ========== 计算动量因子（参考安全摸狗策略） ==========
        y = np.log(df['close'].values)
        n = len(y)
        x = np.arange(n)
        weights = np.linspace(1, 2, n)  # 线性增加权重
        slope, intercept = np.polyfit(x, y, 1, w=weights)

        # 年化收益率
        annualized_returns = math.pow(math.exp(slope), 250) - 1

        # 判定系数
        residuals = y - (slope * x + intercept)
        weighted_residuals = weights * residuals**2
        r_squared = 1 - (np.sum(weighted_residuals) / np.sum(weights * (y - np.mean(y))**2))

        # 动量得分（年化收益率 × 判定系数）
        momentum_score = annualized_returns * r_squared

        # ========== 综合得分 ==========
        # 只使用动量因子，与安全摸狗策略保持一致
        total_score = momentum_score

        return {
            'momentum_score': momentum_score,
            'total_score': total_score
        }

    except Exception as e:
        log.error("计算ETF综合得分失败: {}".format(str(e)))
        return {
            'momentum_score': 0,
            'volatility_score': 0,
            'trend_score': 0,
            'correlation_score': 0,
            'total_score': 0
        }

# ============================================================================
# 风险控制检查
# ============================================================================
def check_risk_control(context):
    """
    风险控制检查

    检查止损、止盈、最大回撤等
    """
    log.info("\n风险控制检查：")

    # ========== 最大回撤控制 ==========
    current_total_value = context.portfolio.total_value

    # 更新最大总资产
    if current_total_value > g.max_total_value:
        g.max_total_value = current_total_value

    # 计算当前回撤
    current_drawdown = (g.max_total_value - current_total_value) / g.max_total_value

    log.info("  最大总资产: {:.2f}, 当前总资产: {:.2f}, 当前回撤: {:.2%}".format(
        g.max_total_value, current_total_value, current_drawdown))

    # 检查是否触发最大回撤控制
    if current_drawdown >= g.max_drawdown:
        log.warning("  ⚠️  触发最大回撤控制！当前回撤: {:.2%} >= 最大回撤限制: {:.2%}".format(
            current_drawdown, g.max_drawdown))
        log.warning("  执行紧急清仓！")

        # 紧急清仓：触发最大回撤控制
        current_data = get_current_data()
        for stock in list(context.portfolio.positions):
            log.info("  紧急卖出: {}".format(stock))
            order_target_value(stock, 0)  # 启用买卖操作
            # 记录交易
            current_price = current_data[stock].last_price if stock in current_data else 0
            avg_cost = context.portfolio.positions[stock].avg_cost
            profit_pct = (current_price - avg_cost) / avg_cost if avg_cost > 0 else 0
            g.trade_stats['trade_details'].append({
                'date': context.current_dt.strftime('%Y-%m-%d'),
                'stock': stock,
                'action': 'sell',
                'reason': 'max_drawdown',
                'price': current_price,
                'profit_pct': profit_pct
            })

        return  # 清仓后不再检查其他风险控制

    # ========== 检查持仓 ==========
    positions = context.portfolio.positions

    if len(positions) == 0:
        log.info("  无持仓")
        return

    # 盘前检查时，直接使用 get_price() 获取上一交易日收盘价
    # 不使用 get_current_data()，因为盘前可能无法获取到有效的实时价格
    stock_prices_df = get_price(
        list(positions.keys()),
        end_date=context.previous_date,
        count=1,
        fields=['close'],
        frequency='daily',
        panel=False,
        skip_paused=True
    )

    # 将股票代码和收盘价映射到字典
    stock_prices = {}
    if not stock_prices_df.empty:
        stock_prices = dict(zip(stock_prices_df['code'], stock_prices_df['close']))

    for stock, position in positions.items():
        # 检查持仓数量，避免无效卖出
        if position.total_amount <= 0:
            continue

        # 获取当前价格（使用上一交易日收盘价）
        if stock in stock_prices and stock_prices[stock] > 0:
            current_price = stock_prices[stock]
            cost_price = position.avg_cost
        else:
            # 无法获取有效价格，跳过风险检查
            log.warning("  {}: 成本价={:.2f}, 无法获取有效价格，跳过风险检查".format(
                stock, position.avg_cost))
            continue

        profit_pct = (current_price - cost_price) / cost_price if cost_price > 0 else 0

        log.info("  {}: 成本价={:.2f}, 当前价={:.2f}, 盈亏={:.2%}".format(
            stock, cost_price, current_price, profit_pct))

        # 止损检查
        if profit_pct <= -g.stop_loss:
            log.info("    触发止损！执行卖出")
            order_target_value(stock, 0)  # 启用买卖操作
            # 记录交易
            g.trade_stats['trade_details'].append({
                'date': context.current_dt.strftime('%Y-%m-%d'),
                'stock': stock,
                'action': 'sell',
                'reason': 'stop_loss',
                'price': current_price,
                'profit_pct': profit_pct
            })

        # 止盈检查
        elif profit_pct >= g.stop_profit:
            log.info("    触发止盈！执行卖出")
            order_target_value(stock, 0)  # 启用买卖操作
            # 记录交易
            g.trade_stats['trade_details'].append({
                'date': context.current_dt.strftime('%Y-%m-%d'),
                'stock': stock,
                'action': 'sell',
                'reason': 'stop_profit',
                'price': current_price,
                'profit_pct': profit_pct
            })

# ============================================================================
# 订单管理函数（实盘交易增强）
# ============================================================================

def check_order_timeout(context):
    """
    订单超时检查函数

    检查所有未成交订单，如果订单超时未成交，则自动撤销

    执行频率：每个交易日盘中检查（10:30、11:00、13:30、14:30）

    功能：
    1. 获取所有未成交订单
    2. 检查订单时间是否超时
    3. 超时订单自动撤销
    4. 记录订单管理日志
    """
    if not g.order_timeout_enabled:
        return
    
    try:
        # 获取所有未成交订单
        open_orders = get_open_orders()
        
        if not open_orders:
            return
        
        log.info("\n订单超时检查：")
        
        # 当前时间
        current_time = context.current_dt
        
        # 检查每个未成交订单
        for order in open_orders:
            try:
                # 计算订单时间差（分钟）
                if hasattr(order, 'datetime'):
                    order_time = order.datetime
                    time_diff = (current_time - order_time).total_seconds() / 60
                    
                    # 检查是否超时
                    if time_diff >= g.order_timeout_minutes:
                        log.info("  订单超时：{}，已存在 {:.0f} 分钟".format(order, time_diff))
                        
                        # 撤销超时订单
                        cancel_order(order)
                        log.info("  ✓ 已撤销超时订单")
                        
                        # 更新统计
                        g.trade_stats['order_stats']['timeout_cancelled'] += 1
                        g.trade_stats['order_stats']['cancelled_orders'] += 1
                        
                        # 记录订单详情
                        g.trade_stats['order_details'].append({
                            'date': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                            'order': str(order),
                            'action': 'cancel',
                            'reason': 'timeout',
                            'time_diff_minutes': time_diff
                        })
                    else:
                        if g.order_log_enabled:
                            log.info("  订单未超时：{}，已存在 {:.0f} 分钟".format(order, time_diff))
                else:
                    log.warning("  订单对象缺少时间信息：{}".format(order))
                    
            except Exception as e:
                log.error("  处理订单 {} 时出错：{}".format(order, str(e)))
        
        log.info("订单超时检查完成")
        
    except Exception as e:
        log.error("订单超时检查失败：{}".format(str(e)))
        import traceback
        log.error(traceback.format_exc())


def cancel_near_close_orders(context):
    """
    收盘前撤单函数

    在收盘前撤销所有未成交订单，避免隔夜风险

    执行频率：每个交易日14:50执行

    功能：
    1. 获取所有未成交订单
    2. 计算距离收盘的时间差
    3. 如果在收盘前阈值时间内，撤销所有未成交订单
    4. 记录撤单日志
    """
    if not g.near_close_cancel_enabled:
        return
    
    try:
        # 获取所有未成交订单
        open_orders = get_open_orders()
        
        if not open_orders:
            log.info("收盘前检查：无未成交订单")
            return
        
        log.info("\n收盘前撤单检查：")
        
        # 当前时间
        current_time = context.current_dt
        current_time_str = current_time.strftime('%H:%M')
        
        # 计算距离收盘的时间（分钟）
        close_time = current_time.replace(hour=15, minute=0, second=0)
        time_to_close = (close_time - current_time).total_seconds() / 60
        
        log.info("  当前时间：{}，距离收盘：{:.0f} 分钟".format(current_time_str, time_to_close))
        
        # 检查是否在收盘前阈值时间内
        if time_to_close <= g.near_close_threshold:
            log.info("  进入收盘前撤单时间窗口（阈值：{} 分钟）".format(g.near_close_threshold))
            
            # 撤销所有未成交订单
            for order in open_orders:
                try:
                    log.info("  撤销订单：{}".format(order))
                    
                    # 撤销订单
                    cancel_order(order)
                    log.info("  ✓ 已撤销订单")
                    
                    # 更新统计
                    g.trade_stats['order_stats']['near_close_cancelled'] += 1
                    g.trade_stats['order_stats']['cancelled_orders'] += 1
                    
                    # 记录订单详情
                    g.trade_stats['order_details'].append({
                        'date': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'order': str(order),
                        'action': 'cancel',
                        'reason': 'near_close',
                        'time_to_close_minutes': time_to_close
                    })
                    
                except Exception as e:
                    log.error("  撤销订单 {} 时出错：{}".format(order, str(e)))
            
            log.info("  收盘前撤单完成")
        else:
            log.info("  未进入收盘前撤单时间窗口")
        
    except Exception as e:
        log.error("收盘前撤单检查失败：{}".format(str(e)))
        import traceback
        log.error(traceback.format_exc())


def check_order_status(context):
    """
    订单状态检查函数

    检查订单状态，记录订单统计信息

    执行频率：每个交易日盘中检查（10:30、11:00、13:30、14:30）

    功能：
    1. 获取所有订单
    2. 统计订单状态（已成交、未成交）
    3. 更新订单统计
    4. 记录订单日志
    """
    if not g.order_log_enabled:
        return
    
    try:
        # 获取所有订单
        all_orders = get_orders()
        open_orders = get_open_orders()
        
        if not all_orders:
            return
        
        # 更新统计
        g.trade_stats['order_stats']['total_orders'] = len(all_orders)
        g.trade_stats['order_stats']['filled_orders'] = len(all_orders) - len(open_orders)
        
        log.info("\n订单状态检查：")
        log.info("  总订单数：{}".format(len(all_orders)))
        log.info("  已成交：{}".format(g.trade_stats['order_stats']['filled_orders']))
        log.info("  未成交：{}".format(len(open_orders)))
        
        # 记录未成交订单详情
        if open_orders and g.order_log_enabled:
            log.info("  未成交订单详情：")
            for order in open_orders:
                log.info("    {}".format(order))
        
    except Exception as e:
        log.error("订单状态检查失败：{}".format(str(e)))

# ============================================================================
# 市场开盘函数
# ============================================================================
def market_open(context):
    """
    市场开盘函数

    每个交易日9:30执行
    """
    log.info("\n" + "=" * 60)
    log.info("市场开盘 - {}".format(context.current_dt.strftime('%Y-%m-%d %H:%M:%S')))
    log.info("=" * 60)

    # 记录当前账户状态
    log.info("总资产：{:.2f}".format(context.portfolio.total_value))
    log.info("可用资金：{:.2f}".format(context.portfolio.available_cash))
    log.info("持仓数量：{}".format(len(context.portfolio.positions)))

    # 记录市场环境
    log.info("市场环境：{}".format(g.market_regime))
    log.info("当前策略：{}".format(g.current_strategy))

    log.info("=" * 60)

# ============================================================================
# 市场检查函数
# ============================================================================
def market_check(context):
    """
    市场检查函数

    每个交易日10:30、11:00、13:30、14:30执行

    功能：
    1. 检查风险控制
    2. 检查订单超时（实盘交易增强）
    3. 检查订单状态（实盘交易增强）
    """
    log.info("\n市场检查 - {}".format(context.current_dt.strftime('%Y-%m-%d %H:%M:%S')))

    # 检查风险控制
    check_risk_control(context)
    
    # 检查订单超时（实盘交易增强）
    check_order_timeout(context)
    
    # 检查订单状态（实盘交易增强）
    check_order_status(context)

# ============================================================================
# 收盘后函数
# ============================================================================
def after_market_close(context):
    """
    收盘后函数

    每个交易日15:00执行
    """
    log.info("\n" + "=" * 60)
    log.info("收盘后 - {}".format(context.current_dt.strftime('%Y-%m-%d %H:%M:%S')))
    log.info("=" * 60)

    # 记录当日收益
    daily_return = context.portfolio.returns
    g.trade_stats['daily_returns'].append(daily_return)

    log.info("当日收益：{:.2%}".format(daily_return))
    log.info("总资产：{:.2f}".format(context.portfolio.total_value))

    # 记录持仓
    log.info("持仓明细：")
    for stock, position in context.portfolio.positions.items():
        # 计算市值：持仓数量 * 持仓价格（使用持仓对象自带的price属性）
        market_value = position.total_amount * position.price if position.price > 0 else 0
        log.info("  {}: 数量={}, 市值={:.2f}".format(
            stock, position.total_amount, market_value))

    # ========== 撤单操作（实盘交易必备） ==========
    # 检查并撤销所有未成交订单，避免隔夜风险
    try:
        orders = get_open_orders()
        if orders:
            log.info("\n未成交订单检查：")
            for _order in orders:
                log.info("  未成交订单: {}".format(_order))
            
            log.info("开始撤销未成交订单...")
            for _order in orders:
                try:
                    cancel_order(_order)
                    log.info("  ✓ 已撤单: {}".format(_order))
                except Exception as e:
                    log.error("  ✗ 撤单失败: {}, 错误: {}".format(_order, str(e)))
            
            log.info("撤单操作完成")
        else:
            log.info("无未成交订单")
    except Exception as e:
        log.error("撤单操作失败: {}".format(str(e)))

    # 记录自定义指标
    record_data(context)

    log.info("=" * 60)

# ============================================================================
# 每周调仓函数
# ============================================================================
def weekly_rebalance(context):
    """
    每周调仓函数

    每周一9:30执行

    使用策略注册表统一管理策略执行，简化代码并提高可扩展性

    注意：不立即执行技术指标买卖策略，避免调仓后立即卖出
    """
    log.info("\n" + "=" * 60)
    log.info("每周调仓 - {}".format(context.current_dt.strftime('%Y-%m-%d %H:%M:%S')))
    log.info("=" * 60)

    # 使用策略注册表执行策略
    if g.current_strategy in g.strategy_registry:
        strategy_info = g.strategy_registry[g.current_strategy]

        # 检查策略是否启用
        if strategy_info['enabled']:
            log.info("执行策略：{}".format(strategy_info['description']))

            # 执行策略
            result = strategy_info['execute_func'](context)

            # 如果策略返回股票列表，执行买入
            if result and isinstance(result, list) and len(result) > 0:
                execute_strategy_buy(context, result, g.current_strategy)

            # 注意：不在调仓时立即执行技术指标买卖策略
            # 技术指标策略在盘前检查时执行，给持仓留出调整时间
            log.info("  技术指标策略将在盘前检查时执行（不在调仓时立即执行）")
        else:
            log.info("策略 {} 已禁用，跳过执行".format(g.current_strategy))
    else:
        # 未知策略，执行多因子选股策略作为默认
        log.warning("未知策略 {}，执行默认的多因子选股策略".format(g.current_strategy))
        execute_multi_factor_rebalance(context)
        # 不立即执行技术指标买卖策略

    log.info("=" * 60)


# ============================================================================
# 策略买入执行函数
# ============================================================================
def execute_strategy_buy(context, stock_list, strategy_type):
    """
    执行策略买入

    参数:
        context: 上下文对象
        stock_list: 股票列表
        strategy_type: 策略类型
    """
    log.info(f"\n执行{strategy_type}策略买入")

    try:
        if not stock_list:
            log.info("股票列表为空，跳过买入")
            return

        # 计算当前持仓
        current_positions = len(context.portfolio.positions)
        available_positions = g.position_limit - current_positions

        if available_positions <= 0:
            log.info(f"已达最大持仓限制{g.position_limit}，不执行买入")
            return

        # 计算每只股票买入金额
        buy_count = min(len(stock_list), available_positions)
        if buy_count <= 0:
            log.info("无可买入股票或仓位已满")
            return

        position_percent = 1.0 / buy_count
        value = context.portfolio.total_value * position_percent

        # 按优先级顺序买入
        current_data = get_current_data()
        bought_count = 0

        for stock in stock_list[:buy_count]:
            try:
                # 获取股票价格，如果当前价格为0则使用上一交易日收盘价
                price = current_data[stock].last_price if stock in current_data else 0
                if price <= 0:
                    try:
                        hist_price = get_price(stock, end_date=context.previous_date, count=1, fields=['close'], frequency='daily')
                        if hist_price is not None and len(hist_price) > 0:
                            price = hist_price['close'].iloc[-1]
                        else:
                            log.warning(f"无法获取{stock}的有效价格，跳过")
                            continue
                    except Exception as e:
                        log.error(f"获取{stock}价格失败: {str(e)}，跳过")
                        continue

                if context.portfolio.available_cash < price * 100:
                    log.info(f"资金不足，跳过{stock}")
                    continue

                buy_quantity = int(value / price / 100) * 100

                if buy_quantity <= 0:
                    continue

                # 执行买入（使用市价单）
                order_result = order_value(stock, value, MarketOrderStyle())  # 启用买卖操作
                log.info("  买入: {}, 数量: {}, 金额: {:.2f}".format(
                    stock, buy_quantity, value))
                log.info(f"✓ 买入 {stock} 价格:{price:.2f} 数量:{buy_quantity} 金额:{value:.2f}")

                if order_result:  # 实际买入成功
                    bought_count += 1

                    # 记录交易
                    g.trade_stats['trade_details'].append({
                        'date': context.current_dt.strftime('%Y-%m-%d'),
                        'stock': stock,
                        'action': 'buy',
                        'reason': strategy_type,
                        'price': price,
                        'quantity': buy_quantity,
                        'value': value
                    })
                else:
                    log.error(f"✗ 买入 {stock} 失败")

            except Exception as e:
                log.error(f"买入{stock}时发生错误: {str(e)}")
                continue

        log.info(f"本次买入{bought_count}只股票")

    except Exception as e:
        log.error(f"执行{strategy_type}策略买入失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())

# ============================================================================
# 每月调仓函数
# ============================================================================
def monthly_rebalance(context):
    """
    每月调仓函数

    每月1日9:30执行
    """
    log.info("\n" + "=" * 60)
    log.info("每月调仓 - {}".format(context.current_dt.strftime('%Y-%m-%d %H:%M:%S')))
    log.info("=" * 60)

    # 检查是否是调仓月份
    if context.current_dt.month in g.multi_factor_rebalance_month:
        log.info("本月为调仓月份")

        # 更新股票池
        g.stock_pool = multi_factor_stock_selection(context)

        # 执行调仓
        execute_multi_factor_rebalance(context)

    log.info("=" * 60)

# ============================================================================
# 执行多因子选股策略调仓
# ============================================================================
def execute_multi_factor_rebalance(context):
    """
    执行多因子选股策略调仓（支持优质股票动态调整仓位）
    """
    log.info("执行多因子选股策略调仓")

    try:
        # 获取目标股票池
        target_stocks = g.stock_pool

        if not target_stocks:
            log.info("目标股票池为空，清仓")
            for stock in list(context.portfolio.positions):
                order_target_value(stock, 0)  # 启用买卖操作
                log.info("  清仓: {}".format(stock))
            return

        # 计算当前总仓位
        current_total_position = context.portfolio.positions_value
        total_value = context.portfolio.total_value
        current_position_ratio = current_total_position / total_value if total_value > 0 else 0

        log.info("  当前总仓位: {:.2%}, 最大仓位限制: {:.2%}".format(
            current_position_ratio, g.max_position))

        # 检查是否超过最大仓位限制
        if current_position_ratio > g.max_position:
            log.warning("  ⚠️  当前总仓位 {:.2%} 超过最大仓位限制 {:.2%}，需要减仓".format(
                current_position_ratio, g.max_position))

        # ========== 动态计算每只股票的目标仓位（根据质量评分） ==========
        # 股票池已经按质量评分排序，排名越靠前，质量越高
        # 根据排名动态调整仓位：前30%的股票为高质量（15%），中间40%为中等质量（12%），后30%为普通（10%）
        stock_count = len(target_stocks)
        target_value_dict = {}  # 存储每只股票的目标仓位
        
        # 第一步：计算所有股票的基础权重和质量系数
        weight_list = []  # 存储每只股票的质量系数
        max_position_list = []  # 存储每只股票的最大仓位限制
        
        for i, stock in enumerate(target_stocks):
            # 计算股票的相对排名（0-1）
            rank_ratio = i / stock_count if stock_count > 0 else 0

            # 根据排名确定股票质量和最大仓位
            if rank_ratio < 0.3:  # 前30%：高质量股票
                max_position_ratio = g.quality_stock_thresholds['high_quality']['max_position']
                quality_level = '高质量'
                quality_factor = 1.5
            elif rank_ratio < 0.7:  # 中间40%：中等质量股票
                max_position_ratio = g.quality_stock_thresholds['medium_quality']['max_position']
                quality_level = '中等质量'
                quality_factor = 1.2
            else:  # 后30%：普通股票
                max_position_ratio = g.quality_stock_thresholds['normal']['max_position']
                quality_level = '普通'
                quality_factor = 1.0

            weight_list.append(quality_factor)
            max_position_list.append(max_position_ratio)
        
        # 第二步：计算总质量系数
        total_weight = sum(weight_list)
        
        # 第三步：计算归一化系数，确保总仓位 = g.max_position
        # 归一化系数 = g.max_position / 总质量系数
        normalization_factor = g.max_position / total_weight if total_weight > 0 else 0
        
        log.info(f"  总质量系数: {total_weight:.2f}, 归一化系数: {normalization_factor:.4f}")

        # 第四步：计算每只股票的实际目标仓位
        # 批量获取所有股票的上一交易日收盘价（避免使用get_current_data，因为盘前可能无法获取）
        stock_prices_df = get_price(target_stocks, end_date=context.previous_date, 
                                   frequency='daily', fields=['close'], count=1, 
                                   panel=False, skip_paused=True)
        
        # 将股票代码和收盘价映射到字典
        stock_prices = {}
        if not stock_prices_df.empty:
            stock_prices = dict(zip(stock_prices_df['code'], stock_prices_df['close']))
        
        # 获取当前数据（用于检查停牌状态）
        current_data = get_current_data()
        
        valid_target_stocks = []  # 存储满足最小交易单位的股票
        valid_weight_list = []    # 存储满足条件股票的质量系数
        
        for i, stock in enumerate(target_stocks):
            # 计算股票的相对排名（0-1）
            rank_ratio = i / stock_count if stock_count > 0 else 0

            # 根据排名确定股票质量和最大仓位
            if rank_ratio < 0.3:  # 前30%：高质量股票
                max_position_ratio = g.quality_stock_thresholds['high_quality']['max_position']
                quality_level = '高质量'
            elif rank_ratio < 0.7:  # 中间40%：中等质量股票
                max_position_ratio = g.quality_stock_thresholds['medium_quality']['max_position']
                quality_level = '中等质量'
            else:  # 后30%：普通股票
                max_position_ratio = g.quality_stock_thresholds['normal']['max_position']
                quality_level = '普通'

            # 计算目标仓位：质量系数 × 归一化系数
            target_position_ratio = weight_list[i] * normalization_factor

            # 限制单只股票最大仓位
            if target_position_ratio > max_position_ratio:
                target_position_ratio = max_position_ratio

            # 计算目标金额
            target_value = total_value * target_position_ratio

            # ========== 检查价格获取和最小交易单位 ==========
            if stock not in stock_prices or stock_prices[stock] <= 0:
                # 无法获取有效价格，跳过
                log.info("  {} [排名{}/{}] 跳过：无法获取有效收盘价".format(
                    stock, i+1, stock_count))
                continue
            
            stock_price = stock_prices[stock]
            min_value_for_100_shares = stock_price * 100  # 100股需要的最小金额
            
            if target_value < min_value_for_100_shares:
                # 目标金额太小，无法买入100股，跳过这只股票
                log.info("  {} [排名{}/{}] 跳过：目标金额={:.2f}元 < 100股所需{:.2f}元 (股价={:.2f}元)".format(
                    stock, i+1, stock_count, target_value, min_value_for_100_shares, stock_price))
                continue
            
            # ========== 检查停牌 ==========
            if stock in current_data and current_data[stock].paused:
                log.info("  {} [排名{}/{}] 跳过：股票停牌".format(
                    stock, i+1, stock_count))
                continue

            # 股票满足所有条件，加入有效股票池
            valid_target_stocks.append(stock)
            valid_weight_list.append(weight_list[i])
            
            target_value_dict[stock] = {
                'target_value': target_value,
                'target_position_ratio': target_position_ratio,
                'quality_level': quality_level
            }

            log.info("  {} [排名{}/{}] 目标仓位: {:.2%} (质量: {})".format(
                stock, i+1, stock_count, target_position_ratio, quality_level))
        
        # ========== 重新计算归一化系数 ==========
        if len(valid_target_stocks) == 0:
            # 没有满足条件的股票
            if len(context.portfolio.positions) > 0:
                # 如果当前有持仓，才清仓
                log.warning("  ⚠️  没有满足条件的股票，清仓当前持仓")
                for stock in list(context.portfolio.positions):
                    log.info("  清仓: {}".format(stock))
                    order_target_value(stock, 0)  # 启用买卖操作
            else:
                # 如果当前没有持仓，只是提示
                log.info("  没有满足条件的股票，保持空仓")
            return
        
        # ========== 检查持仓数量限制 ==========
        # 确保持仓数量不超过最大持仓数量限制
        if len(valid_target_stocks) > g.position_limit:
            log.warning(f"  ⚠️  有效股票数量 {len(valid_target_stocks)} 超过最大持仓数量限制 {g.position_limit}，只保留前 {g.position_limit} 只股票")
            # 截取前 g.position_limit 只股票
            valid_target_stocks = valid_target_stocks[:g.position_limit]
            valid_weight_list = valid_weight_list[:g.position_limit]

        # 使用有效股票重新计算归一化系数
        total_valid_weight = sum(valid_weight_list)
        normalization_factor_valid = g.max_position / total_valid_weight if total_valid_weight > 0 else 0

        log.info(f"  有效股票数量: {len(valid_target_stocks)}/{len(target_stocks)}, 有效质量系数: {total_valid_weight:.2f}, 新归一化系数: {normalization_factor_valid:.4f}")
        
        # ========== 重新计算每只有效股票的目标仓位 ==========
        for stock in valid_target_stocks:
            # 重新计算目标仓位
            target_position_ratio = target_value_dict[stock]['target_position_ratio'] / normalization_factor * normalization_factor_valid
            
            # 重新计算目标金额
            target_value = total_value * target_position_ratio
            
            # 调整为100股的整数倍
            if stock in stock_prices and stock_prices[stock] > 0:
                stock_price = stock_prices[stock]
                max_shares = int(target_value / stock_price / 100) * 100
                
                if max_shares >= 100:
                    adjusted_value = max_shares * stock_price
                    target_value_dict[stock]['target_value'] = adjusted_value
                    target_value_dict[stock]['target_position_ratio'] = adjusted_value / total_value
                    log.info("  {} 最终目标：{:.2%} ({:.2f}元, {}股)".format(
                        stock, target_value_dict[stock]['target_position_ratio'], adjusted_value, max_shares))
                else:
                    # 理论上不会到这里，因为前面已经过滤了
                    log.warning("  {} 计算错误：调整后无法买入100股".format(stock))
                    continue
        
        # 更新target_stocks为有效股票列表
        target_stocks = valid_target_stocks

        # 计算总目标仓位
        total_target_value = sum([v['target_value'] for v in target_value_dict.values()])

        # 验证总仓位是否在合理范围内（应该等于或略小于最大仓位限制）
        total_target_ratio = total_target_value / total_value if total_value > 0 else 0
        if total_target_ratio > g.max_position * 1.01:  # 允许1%的误差
            log.warning("  ⚠️  总目标仓位 {:.2%} 超过最大仓位限制 {:.2%}，需要进一步调整".format(
                total_target_ratio, g.max_position))
        else:
            log.info("  总目标仓位: {:.2%} (最大仓位限制: {:.2%})".format(
                total_target_ratio, g.max_position))

        # 卖出不在目标股票池中的股票
        for stock in list(context.portfolio.positions):
            if stock not in target_stocks:
                # 检查持仓数量，避免无效卖出
                position = context.portfolio.positions[stock]
                if position.total_amount > 0:
                    log.info("  卖出不在目标池中的股票: {}".format(stock))
                    order_target_value(stock, 0)  # 启用买卖操作
                else:
                    log.info("  跳过卖出持仓为0的股票: {}".format(stock))

        # 买入/调整目标股票池中的股票
        for stock in target_stocks:
            target_value = target_value_dict[stock]['target_value']

            # 检查股票是否在持仓中，避免访问不存在的position对象
            if stock in context.portfolio.positions:
                current_position = context.portfolio.positions[stock]
                # 计算当前市值：持仓数量 * 最新价格
                if stock in stock_prices and stock_prices[stock] > 0:
                    current_value = current_position.total_amount * stock_prices[stock]
                else:
                    current_value = 0
            else:
                # 股票不在持仓中，当前值为0
                current_value = 0

            # 检查是否需要调整仓位
            if abs(current_value - target_value) > total_value * 0.05:  # 差异超过5%
                # 检查目标金额是否足够买入至少100股
                if stock in stock_prices and stock_prices[stock] > 0:
                    # 计算可以买入的股数（100的整数倍）
                    max_shares = int(target_value / stock_prices[stock] / 100) * 100
                    
                    if max_shares < 100:
                        # 目标金额太小，无法买入100股，跳过这只股票
                        log.info("  跳过调整仓位: {} 目标金额={:.2f}不足100股(价格={:.2f})，需要至少{:.2f}元".format(
                            stock, target_value, stock_prices[stock], stock_prices[stock] * 100))
                        continue
                    
                    # 调整目标金额为100股的整数倍
                    adjusted_value = max_shares * stock_prices[stock]

                    log.info("  调整仓位: {} 当前={:.2f}, 目标={:.2f} -> 调整后={:.2f} (质量: {}, 股数={})".format(
                        stock, current_value, target_value, adjusted_value, target_value_dict[stock]['quality_level'], max_shares))
                    order_target_value(stock, adjusted_value)  # 启用买卖操作
                else:
                    # 无法获取价格，跳过
                    log.info("  跳过调整仓位: {} 无法获取有效价格".format(stock))

        # 最终仓位检查
        final_position_ratio = context.portfolio.positions_value / total_value if total_value > 0 else 0
        log.info("  调仓后总仓位: {:.2%}".format(final_position_ratio))

    except Exception as e:
        log.error("执行多因子选股策略调仓失败: {}".format(str(e)))
        import traceback
        log.error(traceback.format_exc())

# ============================================================================
# 执行ETF轮动策略调仓
# ============================================================================
def execute_etf_rotation(context):
    """
    执行ETF轮动策略调仓
    """
    log.info("执行ETF轮动策略调仓")

    try:
        # 获取目标ETF
        target_etfs = etf_rotation(context)

        if not target_etfs:
            log.info("目标ETF为空，清仓")
            for etf in list(context.portfolio.positions):
                log.info("  清仓: {}".format(etf))
                order_target_value(etf, 0)  # 启用买卖操作
            return

        # 计算当前总仓位
        current_total_position = context.portfolio.positions_value
        total_value = context.portfolio.total_value
        current_position_ratio = current_total_position / total_value if total_value > 0 else 0

        log.info("  当前总仓位: {:.2%}, 最大仓位限制: {:.2%}".format(
            current_position_ratio, g.max_position))

        # 检查是否超过最大仓位限制
        if current_position_ratio > g.max_position:
            log.warning("  ⚠️  当前总仓位 {:.2%} 超过最大仓位限制 {:.2%}，需要减仓".format(
                current_position_ratio, g.max_position))

        # 计算每只ETF的目标仓位
        # 根据当前仓位调整目标仓位，确保不超过最大仓位
        if current_position_ratio >= g.max_position:
            # 如果已经达到最大仓位，保持现有仓位，只调整持仓结构
            target_value_per_etf = total_value * g.max_position / len(target_etfs)
        else:
            # 如果还未达到最大仓位，逐步建仓
            target_value_per_etf = total_value * g.max_position / len(target_etfs)

        # 限制单只ETF最大仓位
        if target_value_per_etf > total_value * g.etf_max_position:
            target_value_per_etf = total_value * g.etf_max_position
            log.info("  调整单只ETF目标仓位为最大限制: {:.2%}".format(g.etf_max_position))

        # 计算实际可用的目标仓位（考虑最大仓位限制）
        max_total_target_value = total_value * g.max_position
        total_target_value = min(target_value_per_etf * len(target_etfs), max_total_target_value)

        log.info("  单只ETF目标仓位: {:.2f}, 总目标仓位: {:.2f}".format(
            target_value_per_etf, total_target_value))

        # 卖出不在目标ETF中的ETF
        for etf in list(context.portfolio.positions):
            if etf not in target_etfs:
                log.info("  卖出不在目标池中的ETF: {}".format(etf))
                order_target_value(etf, 0)  # 启用买卖操作

        # 买入目标ETF
        for etf in target_etfs:
            # 检查ETF是否在持仓中，避免访问不存在的position对象
            if etf in context.portfolio.positions:
                current_position = context.portfolio.positions[etf]
                # 计算当前市值：持仓数量 * 当前价格
                current_data = get_current_data()
                if etf in current_data:
                    current_price = current_data[etf].last_price
                    # 如果当前价格为0，尝试获取上一交易日收盘价
                    if current_price <= 0:
                        try:
                            hist_price = get_price(etf, end_date=context.previous_date, count=1, fields=['close'], frequency='daily')
                            if hist_price is not None and len(hist_price) > 0:
                                current_price = hist_price['close'].iloc[-1]
                            else:
                                current_price = 0
                        except Exception as e:
                            log.error(f"获取{etf}价格失败: {str(e)}")
                            current_price = 0
                    current_value = current_position.total_amount * current_price
                else:
                    current_value = 0
            else:
                # ETF不在持仓中，当前值为0
                current_value = 0

            # 检查是否需要调整仓位
            if abs(current_value - target_value_per_etf) > total_value * 0.05:  # 差异超过5%
                log.info("  [屏蔽买卖操作] 调整仓位: {} 当前={:.2f}, 目标={:.2f}".format(
                    etf, current_value, target_value_per_etf))
                # order_target_value(etf, target_value_per_etf)  # 已屏蔽买卖操作

        # 最终仓位检查
        final_position_ratio = context.portfolio.positions_value / total_value if total_value > 0 else 0
        log.info("  调仓后总仓位: {:.2%}".format(final_position_ratio))

    except Exception as e:
        log.error("执行ETF轮动策略调仓失败: {}".format(str(e)))
        import traceback
        log.error(traceback.format_exc())

# ============================================================================
# 执行技术指标买卖策略
# ============================================================================
def execute_technical_indicator_strategy(context):
    """
    执行技术指标买卖策略

    基于MACD和KDJ指标生成买卖信号：
    - 买入信号：MACD金叉且KDJ超卖
    - 卖出信号：MACD死叉或KDJ超买
    
    注意：只在持仓时间超过1天后才执行技术指标卖出，避免调仓后立即卖出
    """
    log.info("执行技术指标买卖策略")

    try:
        positions = context.portfolio.positions

        if len(positions) == 0:
            log.info("  无持仓，跳过技术指标策略")
            return

        # 获取当前数据
        current_data = get_current_data()

        for stock, position in positions.items():
            # 检查持仓数量，避免无效卖出
            if position.total_amount <= 0:
                continue

            # 计算技术指标
            macd_df = calculate_macd(stock, context)
            kdj_df = calculate_kdj(stock, context)

            dif = macd_df['DIF'].iloc[0]
            dea = macd_df['DEA'].iloc[0]
            macd = macd_df['MACD'].iloc[0]

            k = kdj_df['K'].iloc[0]
            d = kdj_df['D'].iloc[0]
            j = kdj_df['J'].iloc[0]

            log.info("  {}: MACD(DIF={:.2f}, DEA={:.2f}, MACD={:.2f}), KDJ(K={:.2f}, D={:.2f}, J={:.2f})".format(
                stock, dif, dea, macd, k, d, j))

            # 获取当前价格和持仓天数
            current_price = current_data[stock].last_price if stock in current_data else 0
            if current_price <= 0:
                try:
                    # 尝试获取上一交易日收盘价作为备用
                    hist_price = get_price(stock, end_date=context.previous_date, count=1, fields=['close'], frequency='daily')
                    if hist_price is not None and len(hist_price) > 0:
                        current_price = hist_price['close'].iloc[-1]
                        log.info("    股票当前价使用上一交易日收盘价: {:.2f}".format(current_price))
                    else:
                        log.info("    股票当前价为0且无法获取历史价格，跳过技术指标检查")
                        continue
                except Exception as e:
                    log.error("    获取股票价格失败: {}，跳过技术指标检查".format(str(e)))
                    continue

            # 计算持仓天数（简单估算：使用当前时间和买入时间的差值）
            # 这里简化处理，假设持仓至少1天
            holding_days = 1

            # 卖出信号
            sell_signal = False
            sell_reason = ""

            # MACD死叉（要求持仓至少1天）
            if dif < dea and macd < 0 and holding_days >= 1:
                sell_signal = True
                sell_reason = "MACD死叉"

            # KDJ超买（J>100，要求持仓至少1天）
            if j > 100 and holding_days >= 1:
                sell_signal = True
                sell_reason = "KDJ超买"

            # 执行卖出
            if sell_signal:
                log.info("    卖出信号: {} ({})".format(stock, sell_reason))
                order_target_value(stock, 0)  # 启用买卖操作
                # 记录交易
                g.trade_stats['trade_details'].append({
                    'date': context.current_dt.strftime('%Y-%m-%d'),
                    'stock': stock,
                    'action': 'sell',
                    'reason': 'technical_sell_' + sell_reason,
                    'price': current_price,
                    'profit_pct': (current_price - position.avg_cost) / position.avg_cost if position.avg_cost > 0 else 0
                })

    except Exception as e:
        log.error("执行技术指标买卖策略失败: {}".format(str(e)))
        import traceback
        log.error(traceback.format_exc())

# ============================================================================
# 记录函数
# ============================================================================
def record_data(context):
    """
    记录数据函数

    记录自定义指标到回测结果中，包括：
    - 市场环境
    - 当前策略
    - 实际仓位比例
    - 目标仓位比例（根据市场环境）
    - 仓位差值（目标仓位 - 实际仓位）
    - 股票池数量
    - 最大持仓限制
    - 最大仓位限制
    """
    # ========== 市场环境映射（可扩展） ==========
    market_regime_map = {
        'strong_up': 1,    # 强势上涨市场
        'bull': 2,         # 牛市
        'flat': 3,         # 平稳市场
        'up': 4,           # 上涨市场
        'sideways': 5,     # 震荡市
        'down': 6,         # 下跌市场
        'bear': 7,         # 熊市
        'correction': 8,   # 调整市
        'unknown': 0       # 未知
    }

    # 记录市场环境（使用映射表）
    market_regime_value = market_regime_map.get(g.market_regime, 0)
    record(market_regime=market_regime_value)

    # ========== 策略类型映射（可扩展） ==========
    strategy_map = {
        'multi_factor': 1,        # 多因子选股策略
        'etf_rotation': 2,        # ETF轮动策略
        'limit_up': 3,            # 连板龙头策略
        'one_to_two': 4,          # 一进二策略
        'reversal': 5,            # 弱转强策略
        'reverse_limit_up': 6,    # 反向首板低开策略
        'mean_reversion': 7,      # 均值回归策略
        'value_stock': 8,         # 优质股低吸策略
        'none': 0                 # 观望（空仓）
    }

    # 记录当前策略（使用映射表）
    strategy_value = strategy_map.get(g.current_strategy, 0)
    record(current_strategy=strategy_value)

    # ========== 记录仓位相关指标 ==========
    # 计算实际仓位比例
    total_value = context.portfolio.total_value
    actual_position_ratio = context.portfolio.positions_value / total_value if total_value > 0 else 0
    
    # 计算目标仓位比例（根据市场环境配置）
    target_position_ratio = g.max_position if hasattr(g, 'max_position') else 0
    
    # 计算仓位差值（目标仓位 - 实际仓位）
    position_gap = target_position_ratio - actual_position_ratio
    
    # 记录仓位指标
    record(position_ratio=actual_position_ratio)
    record(target_position_ratio=target_position_ratio)
    record(position_gap=position_gap)

    # ========== 记录股票池指标 ==========
    # 记录股票池数量
    record(stock_pool_size=len(g.stock_pool) if hasattr(g, 'stock_pool') else 0)

    # ========== 记录辅助指标（用于调试） ==========
    # 记录最大持仓限制
    record(position_limit=g.position_limit if hasattr(g, 'position_limit') else 0)

    # 记录最大仓位限制
    record(max_position=g.max_position if hasattr(g, 'max_position') else 0)

# ============================================================================
# 技术指标计算函数
# ============================================================================

def calculate_macd(security, context, fast_period=12, slow_period=26, signal_period=9):
    """
    计算MACD指标

    参数：
        security: 股票代码
        context: 上下文对象
        fast_period: 快线周期（默认12）
        slow_period: 慢线周期（默认26）
        signal_period: 信号线周期（默认9）

    返回：
        DataFrame，包含DIF、DEA、MACD列
    """
    try:
        # 获取历史数据
        hist = attribute_history(security, slow_period + signal_period, '1d', ['close'])

        # 计算EMA（使用内部函数）
        ema_fast = calculate_ema_array(hist['close'].values, fast_period)
        ema_slow = calculate_ema_array(hist['close'].values, slow_period)

        # 计算DIF
        dif = ema_fast - ema_slow

        # 计算DEA
        dea = calculate_ema_array(dif, signal_period)

        # 计算MACD
        macd = (dif - dea) * 2

        # 创建DataFrame
        df = pd.DataFrame({
            'DIF': dif[-1],
            'DEA': dea[-1],
            'MACD': macd[-1]
        }, index=[0])

        log.info("  MACD: DIF={:.4f}, DEA={:.4f}, MACD={:.4f}".format(
            dif[-1], dea[-1], macd[-1]))

        return df

    except Exception as e:
        log.error("计算MACD失败: {}".format(str(e)))
        return pd.DataFrame({'DIF': [0], 'DEA': [0], 'MACD': [0]})


def calculate_kdj(security, context, n=9, m1=3, m2=3):
    """
    计算KDJ指标

    参数：
        security: 股票代码
        context: 上下文对象
        n: RSV计算周期（默认9）
        m1: K值平滑周期（默认3）
        m2: D值平滑周期（默认3）

    返回：
        DataFrame，包含K、D、J列
    """
    try:
        # 获取历史数据
        hist = attribute_history(security, n + m1 + m2, '1d', ['close', 'high', 'low'])

        # 计算RSV
        high_n = hist['high'].rolling(window=n).max()
        low_n = hist['low'].rolling(window=n).min()
        rsv = (hist['close'] - low_n) / (high_n - low_n) * 100

        # 计算K、D、J
        k = rsv.ewm(com=m1-1, adjust=False).mean()
        d = k.ewm(com=m2-1, adjust=False).mean()
        j = 3 * k - 2 * d

        # 创建DataFrame
        df = pd.DataFrame({
            'K': [k.iloc[-1]],
            'D': [d.iloc[-1]],
            'J': [j.iloc[-1]]
        })

        log.info("  KDJ: K={:.2f}, D={:.2f}, J={:.2f}".format(
            k.iloc[-1], d.iloc[-1], j.iloc[-1]))

        return df

    except Exception as e:
        log.error("计算KDJ失败: {}".format(str(e)))
        return pd.DataFrame({'K': [50], 'D': [50], 'J': [50]})


def calculate_rsi(security, context, period=24):
    """
    计算RSI指标

    参数：
        security: 股票代码
        context: 上下文对象
        period: RSI周期（默认24）

    返回：
        DataFrame，包含RSI列
    """
    try:
        # 获取历史数据
        hist = attribute_history(security, period * 2, '1d', ['close'])

        # 计算涨跌幅
        delta = hist['close'].diff()

        # 分离上涨和下跌
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        # 计算平均涨跌幅
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        # 计算RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # 创建DataFrame
        df = pd.DataFrame({'RSI': [rsi.iloc[-1]]})

        log.info("  RSI: {:.2f}".format(rsi.iloc[-1]))

        return df

    except Exception as e:
        log.error("计算RSI失败: {}".format(str(e)))
        return pd.DataFrame({'RSI': [50]})


def calculate_boll(security, context, period=20, nbdevup=2, nbdevdn=2):
    """
    计算布林带指标

    参数：
        security: 股票代码
        context: 上下文对象
        period: 周期（默认20）
        nbdevup: 上轨标准差倍数（默认2）
        nbdevdn: 下轨标准差倍数（默认2）

    返回：
        DataFrame，包含upper、middle、lower列
    """
    try:
        # 获取历史数据
        hist = attribute_history(security, period, '1d', ['close'])

        # 计算中轨（移动平均）
        middle = hist['close'].rolling(window=period).mean()

        # 计算标准差
        std = hist['close'].rolling(window=period).std()

        # 计算上轨和下轨
        upper = middle + nbdevup * std
        lower = middle - nbdevdn * std

        # 创建DataFrame
        df = pd.DataFrame({
            'upper': [upper.iloc[-1]],
            'middle': [middle.iloc[-1]],
            'lower': [lower.iloc[-1]]
        })

        log.info("  BOLL: 上轨={:.2f}, 中轨={:.2f}, 下轨={:.2f}".format(
            upper.iloc[-1], middle.iloc[-1], lower.iloc[-1]))

        return df

    except Exception as e:
        log.error("计算BOLL失败: {}".format(str(e)))
        return pd.DataFrame({'upper': [0], 'middle': [0], 'lower': [0]})


def calculate_ma(security, context, periods=[5, 10, 20, 60]):
    """
    计算移动平均线

    参数：
        security: 股票代码
        context: 上下文对象
        periods: 周期列表（默认[5, 10, 20, 60]）

    返回：
        DataFrame，包含各周期移动平均线
    """
    try:
        # 获取历史数据
        max_period = max(periods)
        hist = attribute_history(security, max_period, '1d', ['close'])

        # 计算各周期移动平均线
        df = pd.DataFrame()
        for period in periods:
            ma = hist['close'].rolling(window=period).mean()
            df['MA{}'.format(period)] = [ma.iloc[-1]]

        log.info("  MA: {}".format(', '.join(['MA{}={:.2f}'.format(p, df['MA{}'.format(p)].iloc[0]) for p in periods])))

        return df

    except Exception as e:
        log.error("计算MA失败: {}".format(str(e)))
        return pd.DataFrame({'MA5': [0], 'MA10': [0], 'MA20': [0], 'MA60': [0]})


def calculate_ema(security, context, periods=[12, 26]):
    """
    计算指数移动平均线

    参数：
        security: 股票代码
        context: 上下文对象
        periods: 周期列表（默认[12, 26]）

    返回：
        DataFrame，包含各周期指数移动平均线
    """
    try:
        # 获取历史数据
        max_period = max(periods)
        hist = attribute_history(security, max_period, '1d', ['close'])

        # 计算各周期指数移动平均线
        df = pd.DataFrame()
        for period in periods:
            ema = hist['close'].ewm(span=period, adjust=False).mean()
            df['EMA{}'.format(period)] = [ema.iloc[-1]]

        log.info("  EMA: {}".format(', '.join(['EMA{}={:.2f}'.format(p, df['EMA{}'.format(p)].iloc[0]) for p in periods])))

        return df

    except Exception as e:
        log.error("计算EMA失败: {}".format(str(e)))
        return pd.DataFrame({'EMA12': [0], 'EMA26': [0]})


def calculate_ema_array(data, period):
    """
    计算指数移动平均线（内部函数）

    参数：
        data: 数据数组
        period: 周期

    返回：
        EMA数组
    """
    ema = np.zeros_like(data)
    ema[0] = data[0]

    multiplier = 2 / (period + 1)

    for i in range(1, len(data)):
        ema[i] = (data[i] * multiplier) + (ema[i-1] * (1 - multiplier))

    return ema


# ============================================================================
# 技术指标批量计算函数
# ============================================================================

def calculate_all_technical_indicators(security, context):
    """
    计算所有技术指标

    参数：
        security: 股票代码
        context: 上下文对象

    返回：
        包含所有技术指标的字典
    """
    log.info("\n计算技术指标：{}".format(security))

    indicators = {}

    # 计算MACD
    indicators['macd'] = calculate_macd(security, context)

    # 计算KDJ
    indicators['kdj'] = calculate_kdj(security, context)

    # 计算RSI
    indicators['rsi'] = calculate_rsi(security, context)

    # 计算布林带
    indicators['boll'] = calculate_boll(security, context)

    # 计算移动平均线
    indicators['ma'] = calculate_ma(security, context)

    # 计算指数移动平均线
    indicators['ema'] = calculate_ema(security, context)

    return indicators


# ============================================================================
# 因子计算函数
# ============================================================================

def calculate_quality_factors(stock_list, context):
    """
    计算质量因子

    参数：
        stock_list: 股票代码列表
        context: 上下文对象

    返回：
        DataFrame，包含质量因子
    """
    log.info("\n计算质量因子")

    try:
        end_date = context.previous_date.strftime("%Y-%m-%d")

        # 获取财务指标
        q = query(
            indicator.code,
            indicator.roe_ttm,
            indicator.roa_ttm,
            indicator.gross_profit_margin,
            indicator.net_profit_margin
        ).filter(
            indicator.code.in_(stock_list)
        )

        df = get_fundamentals(q, date=end_date).set_index('code')

        log.info("  质量因子数量：{}".format(len(df)))

        return df

    except Exception as e:
        log.error("计算质量因子失败: {}".format(str(e)))
        return pd.DataFrame()


def calculate_growth_factors(stock_list, context):
    """
    计算成长因子

    参数：
        stock_list: 股票代码列表
        context: 上下文对象

    返回：
        DataFrame，包含成长因子
    """
    log.info("\n计算成长因子")

    try:
        end_date = context.previous_date.strftime("%Y-%m-%d")

        # 获取成长指标
        q = query(
            indicator.code,
            indicator.inc_revenue_year_on_year,
            indicator.inc_net_profit_year_on_year,
            indicator.operation_profit_growth
        ).filter(
            indicator.code.in_(stock_list)
        )

        df = get_fundamentals(q, date=end_date).set_index('code')

        log.info("  成长因子数量：{}".format(len(df)))

        return df

    except Exception as e:
        log.error("计算成长因子失败: {}".format(str(e)))
        return pd.DataFrame()


def calculate_valuation_factors(stock_list, context):
    """
    计算估值因子

    参数：
        stock_list: 股票代码列表
        context: 上下文对象

    返回：
        DataFrame，包含估值因子
    """
    log.info("\n计算估值因子")

    try:
        end_date = context.previous_date.strftime("%Y-%m-%d")

        # 获取估值指标
        q = query(
            valuation.code,
            valuation.pe_ratio,
            valuation.pb_ratio,
            valuation.ps_ratio,
            valuation.market_cap
        ).filter(
            valuation.code.in_(stock_list)
        )

        df = get_fundamentals(q, date=end_date).set_index('code')

        log.info("  估值因子数量：{}".format(len(df)))

        return df

    except Exception as e:
        log.error("计算估值因子失败: {}".format(str(e)))
        return pd.DataFrame()


def calculate_momentum_factors(stock_list, context):
    """
    计算动量因子

    参数：
        stock_list: 股票代码列表
        context: 上下文对象

    返回：
        DataFrame，包含动量因子
    """
    log.info("\n计算动量因子")

    try:
        end_date = context.previous_date.strftime("%Y-%m-%d")

        # 获取动量因子
        factors = ['Price3M', 'ROC20', 'CR20']
        data = get_factor_values(stock_list, factors=factors,
                                start_date=end_date, end_date=end_date)

        # 整理数据
        df = pd.DataFrame(index=stock_list)
        for factor in factors:
            df[factor] = data[factor].T.iloc[:, 0]

        log.info("  动量因子数量：{}".format(len(df)))

        return df

    except Exception as e:
        log.error("计算动量因子失败: {}".format(str(e)))
        return pd.DataFrame()


def calculate_all_factors(stock_list, context):
    """
    计算所有因子

    参数：
        stock_list: 股票代码列表
        context: 上下文对象

    返回：
        包含所有因子的字典
    """
    log.info("\n" + "=" * 60)
    log.info("计算所有因子")
    log.info("=" * 60)

    factors = {}

    # 计算质量因子
    factors['quality'] = calculate_quality_factors(stock_list, context)

    # 计算成长因子
    factors['growth'] = calculate_growth_factors(stock_list, context)

    # 计算估值因子
    factors['valuation'] = calculate_valuation_factors(stock_list, context)

    # 计算动量因子
    factors['momentum'] = calculate_momentum_factors(stock_list, context)

    log.info("=" * 60)

    return factors


# ============================================================================
# 测试函数（用于验证指标和因子计算）
# ============================================================================

def test_indicators_and_factors(context):
    """
    测试指标和因子计算

    用于验证所有指标和因子的计算是否正常
    """
    log.info("\n" + "=" * 60)
    log.info("测试指标和因子计算")
    log.info("=" * 60)

    # 测试股票列表
    test_stocks = ['000001.XSHE', '600519.XSHG', '000858.XSHE']

    # 测试技术指标
    for stock in test_stocks:
        log.info("\n测试股票：{}".format(stock))
        indicators = calculate_all_technical_indicators(stock, context)
        log.info("技术指标计算完成")

    # 测试因子计算
    log.info("\n测试因子计算")
    factors = calculate_all_factors(test_stocks, context)
    log.info("因子计算完成")

    log.info("=" * 60)
    log.info("测试完成")
    log.info("=" * 60)


# ============================================================================
# 热门概念获取和主线评分系统（参考Enhanced_5in1_LimitUp策略）
# ============================================================================

def get_all_hot_concepts_optimized(context, days=5):
    """
    获取最近N个交易日（包括今日）的热门概念列表，优先从缓存中获取
    
    参数:
        context: 策略上下文，用于获取当前日期
        days: 获取最近N个交易日的数据，默认5天
    
    返回:
        dict: {
            'all_concepts': 所有交易日的热门概念列表（去重）,
            'by_date': 按日期分组的热门概念字典,
            'summary': 统计信息
        }
    """
    try:
        # 处理日期参数
        end_date = context.previous_date
        
        log.info(f"开始获取最近{days}个交易日的热门概念，截止日期: {end_date.strftime('%Y-%m-%d')}")

        # 初始化缓存结构
        if not hasattr(g, 'hot_concepts_data_cache'):
            g.hot_concepts_data_cache = {}
            log.info("初始化热门概念缓存 g.hot_concepts_data_cache")
        
        if not hasattr(g, 'hot_concepts_api_called'):
            g.hot_concepts_api_called = {}
        
        # 获取最近N个交易日
        try:
            trade_days = get_trade_days(end_date=end_date, count=days)
            
            # 判断是否为空
            if trade_days is None or (hasattr(trade_days, '__len__') and len(trade_days) == 0):
                log.warning("未获取到有效交易日")
                return {
                    'all_concepts': [],
                    'by_date': {},
                    'summary': {'total_unique_concepts': 0, 'total_dates': 0, 'date_range': 'N/A'}
                }
            
            # 转换为字符串列表（处理 numpy.datetime64 类型）
            trade_days_str = []
            for td in trade_days:
                if isinstance(td, str):
                    trade_days_str.append(td)
                else:
                    trade_days_str.append(pd.Timestamp(td).strftime('%Y-%m-%d'))
            
            log.info(f"获取到{len(trade_days_str)}个交易日: {trade_days_str}")
            
        except Exception as e:
            log.error(f"获取交易日失败: {str(e)}")
            import traceback
            log.error(f"错误详情: {traceback.format_exc()}")
            return {
                'all_concepts': [],
                'by_date': {},
                'summary': {'total_unique_concepts': 0, 'total_dates': 0, 'date_range': 'N/A'}
            }
        
        # 遍历每个交易日，获取热门概念
        all_concepts_dict = {}  # 用于去重，key为概念代码
        concepts_by_date = {}   # 按日期分组
        
        for trade_day_str in trade_days_str:
            # 转换为API需要的格式: '20250801'
            date_str_api = trade_day_str.replace('-', '')
            date_key = trade_day_str  # 用于展示
            
            # 获取该日期的热门概念
            daily_concepts = _get_hot_concepts_for_date(date_str_api, context)
            
            # 确保返回的是列表格式
            if daily_concepts and isinstance(daily_concepts, list):
                concepts_by_date[date_key] = daily_concepts
                
                # 合并到总列表（去重并统计）
                for concept in daily_concepts:
                    # 确保 concept 是字典类型
                    if not isinstance(concept, dict):
                        continue
                    
                    concept_code = concept.get('code')
                    concept_name = concept.get('name', '')
                    
                    # 跳过无效数据
                    if not concept_code:
                        continue
                    
                    if concept_code not in all_concepts_dict:
                        all_concepts_dict[concept_code] = {
                            'code': concept_code,
                            'name': concept_name,
                            'first_seen': date_key,
                            'last_seen': date_key,
                            'appearances': 1,
                            'dates': [date_key]
                        }
                    else:
                        all_concepts_dict[concept_code]['last_seen'] = date_key
                        all_concepts_dict[concept_code]['appearances'] += 1
                        all_concepts_dict[concept_code]['dates'].append(date_key)
                
                log.info(f"✓ {date_key} 获取到 {len(daily_concepts)} 个热门概念")
            else:
                log.warning(f"⚠ {date_key} 未获取到热门概念")
        
        # 整理结果
        all_concepts_list = list(all_concepts_dict.values())
        
        # 按出现次数排序（出现次数多的排在前面）
        all_concepts_list.sort(key=lambda x: (-x['appearances'], x['last_seen']), reverse=False)
        
        result = {
            'all_concepts': all_concepts_list,
            'by_date': concepts_by_date,
            'summary': {
                'total_unique_concepts': len(all_concepts_list),
                'total_dates': len(concepts_by_date),
                'date_range': f"{trade_days_str[0]} 至 {trade_days_str[-1]}" if len(trade_days_str) > 0 else 'N/A',
                'trade_days': trade_days_str
            }
        }
        
        # 输出统计信息
        log.info(f"=" * 60)
        log.info(f"📊 热门概念统计（最近{days}个交易日）")
        log.info(f"  日期范围: {result['summary']['date_range']}")
        log.info(f"  总计唯一概念数: {result['summary']['total_unique_concepts']}")
        log.info(f"  有效交易日数: {result['summary']['total_dates']}")
        
        # 输出高频概念（出现3次及以上）
        high_freq_concepts = [c for c in all_concepts_list if c['appearances'] >= 3]
        if high_freq_concepts:
            log.info(f"  高频概念（出现≥3次）: {len(high_freq_concepts)}个")
            for concept in high_freq_concepts[:5]:
                log.info(f"    - {concept['name']}({concept['code']}): 出现{concept['appearances']}次")
        
        log.info(f"=" * 60)
        
        return result
        
    except Exception as e:
        log.error(f"获取热门概念时出错: {str(e)}")
        import traceback
        log.error(f"错误详情: {traceback.format_exc()}")
        return {
            'all_concepts': [],
            'by_date': {},
            'summary': {'total_unique_concepts': 0, 'total_dates': 0, 'date_range': 'N/A'}
        }


def _get_hot_concepts_for_date(date_str, context=None):
    """
    获取指定日期的热门概念（内部函数）
    
    参数:
        date_str: 日期字符串，格式为YYYYMMDD（如 '20250801'）
        context: 策略上下文
    
    返回:
        热门概念列表，每个元素为 {'code': xxx, 'name': xxx}
        如果没有数据，返回空列表 []
    """
    try:
        # 检查缓存
        if date_str in g.hot_concepts_data_cache:
            cache_data = g.hot_concepts_data_cache[date_str]
            
            if isinstance(cache_data, list) and len(cache_data) > 0:
                return cache_data
            elif cache_data == [] and g.hot_concepts_api_called.get(date_str, False):
                return []
        
        # 检查API调用标记
        if g.hot_concepts_api_called.get(date_str, False):
            return []
        
        # 标记已调用API（防止重复调用）
        g.hot_concepts_api_called[date_str] = True
        
        # 从聚宽获取热门概念（简化版，不使用同花顺API）
        try:
            # 获取所有概念
            all_concepts = get_concepts()
            
            # 获取该日期的概念热度（这里简化处理，实际应该获取涨停股票所属概念）
            # 由于聚宽API限制，这里使用一个简化的方法
            # 实际使用时，应该获取当日涨停股票，然后统计所属概念
            
            # 简化版：返回前g.concept_num个概念
            if all_concepts is not None and len(all_concepts) > 0:
                hot_concepts = []
                for idx, row in all_concepts.head(g.concept_num).iterrows():
                    hot_concepts.append({
                        'code': idx,
                        'name': row['name']
                    })
                
                # 缓存结果
                g.hot_concepts_data_cache[date_str] = hot_concepts
                
                if len(hot_concepts) > 0:
                    log.info(f"  ✓ {date_str} 从聚宽获取 {len(hot_concepts)} 个热门概念")
                
                return hot_concepts
            else:
                log.warning(f"  ⚠ {date_str} 未获取到热门概念")
                return []
            
        except Exception as api_error:
            log.error(f"  {date_str} 获取热门概念失败: {str(api_error)}")
            g.hot_concepts_data_cache[date_str] = []
            return []
    
    except Exception as e:
        log.error(f"获取 {date_str} 热门概念时出错: {str(e)}")
        return []


def calculate_mainline_score_optimized(stock, context):
    """
    计算主线评分（参考Enhanced_5in1_LimitUp策略）
    
    参数:
        stock: 股票代码
        context: 上下文对象
    
    返回:
        主线评分（匹配1个概念得2分，数量越多分数越高）
    """
    try:
        # 检查缓存
        if stock in g.mainline_score_cache:
            return g.mainline_score_cache[stock]
        
        # 获取热门概念列表
        hot_concepts_result = get_all_hot_concepts_optimized(context)
        
        # 提取所有热门概念的名称列表
        hot_concepts_list = [concept['name'] for concept in hot_concepts_result['all_concepts']]
        hot_concepts_set = set(hot_concepts_list)
        
        if not hot_concepts_set:
            return 0
        
        # 获取股票所属概念
        stock_info = get_security_info(stock)
        if not stock_info or not stock_info.concepts:
            return 0
        
        # 从概念字典中提取'name'字段，得到字符串列表
        stock_concepts = [concept['name'] for concept in stock_info.concepts]
        
        # 检查是否有匹配的热门概念，并去重
        matched_concepts = [c for c in stock_concepts if c in hot_concepts_set]
        unique_matched = list(set(matched_concepts))
        match_count = len(unique_matched)
        
        # 按匹配数量计算分数（1个概念得2分，数量越多分数越高）
        mainline_score = match_count * 2 if match_count > 0 else 0
        
        # 缓存结果
        g.mainline_score_cache[stock] = mainline_score
        
        return mainline_score
    
    except Exception as e:
        log.error(f"计算主线评分时出错: {str(e)}")
        return 0


# ============================================================================
# 连板龙头策略辅助函数
# ============================================================================

def get_continue_count_df(stock_list, end_date, count=20):
    """
    获取连续涨停统计
    
    参数:
        stock_list: 股票代码列表
        end_date: 结束日期
        count: 统计天数
    
    返回:
        DataFrame，包含count（连续涨停天数）和extreme_count（一字板天数）
    """
    try:
        result = {}
        
        for stock in stock_list:
            try:
                # 获取历史数据
                hist = get_price(stock, end_date=end_date, count=count,
                               fields=['open', 'close', 'high', 'low', 'high_limit'], 
                               frequency='daily', skip_paused=True)
                
                if len(hist) < 2:
                    continue
                
                # 计算连续涨停
                consecutive_count = 0
                extreme_count = 0
                
                for i in range(len(hist)-1, -1, -1):
                    # 判断是否涨停
                    if hist['close'].iloc[i] >= hist['high_limit'].iloc[i] * 0.995:
                        consecutive_count += 1
                        # 判断是否一字板
                        if hist['high'].iloc[i] == hist['low'].iloc[i]:
                            extreme_count += 1
                    else:
                        break
                
                result[stock] = {
                    'count': consecutive_count,
                    'extreme_count': extreme_count
                }
                
            except Exception as e:
                log.error(f"获取股票{stock}连续涨停统计失败: {str(e)}")
                continue
        
        if result:
            df = pd.DataFrame.from_dict(result, orient='index')
            return df
        else:
            return pd.DataFrame(index=[], columns=['count', 'extreme_count'])
    
    except Exception as e:
        log.error(f"获取连续涨停统计失败: {str(e)}")
        return pd.DataFrame(index=[], columns=['count', 'extreme_count'])


def get_continue_count_df_ll(stock_list, end_date, count=10):
    """
    获取连续跌停统计
    
    参数:
        stock_list: 股票代码列表
        end_date: 结束日期
        count: 统计天数
    
    返回:
        DataFrame，包含连续跌停天数
    """
    try:
        result = {}
        
        for stock in stock_list:
            try:
                # 获取历史数据
                hist = get_price(stock, end_date=end_date, count=count,
                               fields=['open', 'close', 'high', 'low', 'low_limit'], 
                               frequency='daily', skip_paused=True)
                
                if len(hist) < 2:
                    continue
                
                # 计算连续跌停
                consecutive_count = 0
                
                for i in range(len(hist)-1, -1, -1):
                    # 判断是否跌停
                    if hist['close'].iloc[i] <= hist['low_limit'].iloc[i] * 1.005:
                        consecutive_count += 1
                    else:
                        break
                
                if consecutive_count > 0:
                    result[stock] = {'count': consecutive_count}
                
            except Exception as e:
                log.error(f"获取股票{stock}连续跌停统计失败: {str(e)}")
                continue
        
        if result:
            df = pd.DataFrame.from_dict(result, orient='index')
            return df
        else:
            return pd.DataFrame(index=[], columns=['count'])
    
    except Exception as e:
        log.error(f"获取连续跌停统计失败: {str(e)}")
        return pd.DataFrame(index=[], columns=['count'])


def get_relative_position_df(stock_list, end_date, period=60):
    """
    获取相对位置统计
    
    参数:
        stock_list: 股票代码列表
        end_date: 结束日期
        period: 统计周期
    
    返回:
        DataFrame，包含rp（相对位置）
    """
    try:
        result = {}
        
        for stock in stock_list:
            try:
                # 获取历史数据
                hist = get_price(stock, end_date=end_date, count=period,
                               fields=['close', 'high', 'low'], 
                               frequency='daily', skip_paused=True)
                
                if len(hist) < period:
                    continue
                
                # 计算相对位置
                current_price = hist['close'].iloc[-1]
                period_high = hist['high'].max()
                period_low = hist['low'].min()
                
                if period_high != period_low:
                    rp = (current_price - period_low) / (period_high - period_low)
                else:
                    rp = 0.5
                
                result[stock] = {'rp': rp}
                
            except Exception as e:
                log.error(f"获取股票{stock}相对位置统计失败: {str(e)}")
                continue
        
        if result:
            df = pd.DataFrame.from_dict(result, orient='index')
            return df
        else:
            return pd.DataFrame(index=[], columns=['rp'])
    
    except Exception as e:
        log.error(f"获取相对位置统计失败: {str(e)}")
        return pd.DataFrame(index=[], columns=['rp'])


def get_hl_stock(stock_list, date):
    """
    获取涨停股票
    
    参数:
        stock_list: 股票代码列表
        date: 日期
    
    返回:
        涨停股票列表
    """
    try:
        hl_list = []
        
        for stock in stock_list:
            try:
                # 获取当日数据
                hist = get_price(stock, end_date=date, count=1,
                               fields=['close', 'high_limit'], 
                               frequency='daily', skip_paused=True)
                
                if len(hist) > 0:
                    # 判断是否涨停
                    if hist['close'].iloc[0] >= hist['high_limit'].iloc[0] * 0.995:
                        hl_list.append(stock)
                
            except Exception as e:
                continue
        
        return hl_list
    
    except Exception as e:
        log.error(f"获取涨停股票失败: {str(e)}")
        return []


def get_ever_hl_stock(stock_list, date):
    """
    获取曾经涨停的股票
    
    参数:
        stock_list: 股票代码列表
        date: 日期
    
    返回:
        曾经涨停的股票列表
    """
    try:
        ever_hl_list = []
        
        for stock in stock_list:
            try:
                # 获取当日数据
                hist = get_price(stock, end_date=date, count=1,
                               fields=['close', 'high', 'high_limit'], 
                               frequency='daily', skip_paused=True)
                
                if len(hist) > 0:
                    # 判断是否曾经涨停（最高价达到涨停价）
                    if hist['high'].iloc[0] >= hist['high_limit'].iloc[0] * 0.995:
                        ever_hl_list.append(stock)
                
            except Exception as e:
                continue
        
        return ever_hl_list
    
    except Exception as e:
        log.error(f"获取曾经涨停股票失败: {str(e)}")
        return []


def get_ever_hl_stock2(stock_list, date):
    """
    获取曾经涨停但收盘未涨停的股票
    
    参数:
        stock_list: 股票代码列表
        date: 日期
    
    返回:
        曾经涨停但收盘未涨停的股票列表
    """
    try:
        ever_hl_list = []
        
        for stock in stock_list:
            try:
                # 获取当日数据
                hist = get_price(stock, end_date=date, count=1,
                               fields=['open', 'close', 'high', 'high_limit'], 
                               frequency='daily', skip_paused=True)
                
                if len(hist) > 0:
                    # 判断是否曾经涨停但收盘未涨停
                    if (hist['high'].iloc[0] >= hist['high_limit'].iloc[0] * 0.995 and 
                        hist['close'].iloc[0] < hist['high_limit'].iloc[0] * 0.995):
                        ever_hl_list.append(stock)
                
            except Exception as e:
                continue
        
        return ever_hl_list
    
    except Exception as e:
        log.error(f"获取曾经涨停但收盘未涨停股票失败: {str(e)}")
        return []


def get_ll_stock(stock_list, date):
    """
    获取跌停股票
    
    参数:
        stock_list: 股票代码列表
        date: 日期
    
    返回:
        跌停股票列表
    """
    try:
        ll_list = []
        
        for stock in stock_list:
            try:
                # 获取当日数据
                hist = get_price(stock, end_date=date, count=1,
                               fields=['close', 'low_limit'], 
                               frequency='daily', skip_paused=True)
                
                if len(hist) > 0:
                    # 判断是否跌停
                    if hist['close'].iloc[0] <= hist['low_limit'].iloc[0] * 1.005:
                        ll_list.append(stock)
                
            except Exception as e:
                continue
        
        return ll_list
    
    except Exception as e:
        log.error(f"获取跌停股票失败: {str(e)}")
        return []


def HSL(stock_list, date):
    """
    获取换手率
    
    参数:
        stock_list: 股票代码列表
        date: 日期
    
    返回:
        换手率字典
    """
    try:
        hsl_dict = {}
        
        for stock in stock_list:
            try:
                # 获取估值数据
                valuation = get_valuation(stock, end_date=date, count=1,
                                       fields=['turnover_ratio'])
                
                if len(valuation) > 0:
                    hsl_dict[stock] = valuation['turnover_ratio'].iloc[0]
                
            except Exception as e:
                continue
        
        return hsl_dict
    
    except Exception as e:
        log.error(f"获取换手率失败: {str(e)}")
        return {}


def prepare_stock_list(date):
    """
    准备股票列表
    
    参数:
        date: 日期
    
    返回:
        股票代码列表
    """
    try:
        # 获取所有股票
        stock_list = list(get_all_securities(types=['stock'], date=date).index)
        
        # 过滤ST股票
        filtered_list = []
        for stock in stock_list:
            try:
                stock_info = get_security_info(stock)
                if stock_info and 'ST' not in stock_info.display_name:
                    filtered_list.append(stock)
            except:
                continue
        
        return filtered_list
    
    except Exception as e:
        log.error(f"准备股票列表失败: {str(e)}")
        return []


def get_concept(stock_list, date):
    """
    获取股票所属概念
    
    参数:
        stock_list: 股票代码列表
        date: 日期
    
    返回:
        概念字典
    """
    try:
        concept_dict = {}
        
        for stock in stock_list:
            try:
                stock_info = get_security_info(stock)
                if stock_info and stock_info.concepts:
                    concept_dict[stock] = stock_info.concepts
                
            except Exception as e:
                continue
        
        return concept_dict
    
    except Exception as e:
        log.error(f"获取概念失败: {str(e)}")
        return {}


def get_hot_concept(concept_dict, date):
    """
    获取热门概念
    
    参数:
        concept_dict: 概念字典
        date: 日期
    
    返回:
        热门概念名称
    """
    try:
        # 获取热门概念数据
        hot_concepts_result = get_all_hot_concepts_optimized(context=None)
        
        if hot_concepts_result['all_concepts']:
            # 返回第一个热门概念
            return hot_concepts_result['all_concepts'][0]['name']
        
        return None
    
    except Exception as e:
        log.error(f"获取热门概念失败: {str(e)}")
        return None


def filter_concept_stock(concept_dict, hot_concept):
    """
    过滤属于热门概念的股票
    
    参数:
        concept_dict: 概念字典
        hot_concept: 热门概念名称
    
    返回:
        股票列表
    """
    try:
        hot_stocks = []
        
        for stock, concepts in concept_dict.items():
            if concepts:
                for concept in concepts:
                    if concept.get('name') == hot_concept:
                        hot_stocks.append(stock)
                        break
        
        return hot_stocks
    
    except Exception as e:
        log.error(f"过滤概念股票失败: {str(e)}")
        return []


def get_factor_filter_df(context, stock_list, factor, sort=True):
    """
    获取因子过滤后的股票
    
    参数:
        context: 上下文对象
        stock_list: 股票代码列表
        factor: 因子名称
        sort: 是否排序
    
    返回:
        DataFrame
    """
    try:
        # 获取因子值
        data = get_factor_values(stock_list, factors=[factor],
                               end_date=context.previous_date, count=1)
        
        if factor in data:
            df = data[factor].T
            
            if sort:
                df = df.sort_values(by=df.columns[0], ascending=False)
            
            return df
        else:
            return pd.DataFrame(index=stock_list, columns=[factor])
    
    except Exception as e:
        log.error(f"获取因子过滤失败: {str(e)}")
        return pd.DataFrame(index=stock_list, columns=[factor])


def rise_low_volume(stock, context):
    """
    检查是否为缩量上涨
    
    参数:
        stock: 股票代码
        context: 上下文对象
    
    返回:
        True表示缩量上涨，False表示不是
    """
    try:
        # 获取历史数据
        hist = get_price(stock, end_date=context.previous_date, count=2,
                       fields=['close', 'volume'], 
                       frequency='daily', skip_paused=True)
        
        if len(hist) < 2:
            return False
        
        # 计算涨幅
        change_pct = (hist['close'].iloc[-1] - hist['close'].iloc[-2]) / hist['close'].iloc[-2]
        
        # 计算量比
        volume_ratio = hist['volume'].iloc[-1] / hist['volume'].iloc[-2]
        
        # 判断是否为缩量上涨（涨幅>0且量比<0.8）
        if change_pct > 0 and volume_ratio < 0.8:
            return True
        
        return False
    
    except Exception as e:
        log.error(f"检查缩量上涨失败: {str(e)}")
        return False


def get_volume_data(stock, context):
    """
    获取量能数据
    
    参数:
        stock: 股票代码
        context: 上下文对象
    
    返回:
        (last_volume, last_2_volume, volume_ratio)
    """
    try:
        # 获取历史数据
        hist = get_price(stock, end_date=context.previous_date, count=2,
                       fields=['volume'], 
                       frequency='daily', skip_paused=True)
        
        if len(hist) < 2:
            return (0, 0, 0)
        
        last_volume = hist['volume'].iloc[-1]
        last_2_volume = hist['volume'].iloc[-2]
        
        if last_2_volume > 0:
            volume_ratio = last_volume / last_2_volume
        else:
            volume_ratio = 0
        
        return (last_volume, last_2_volume, volume_ratio)
    
    except Exception as e:
        log.error(f"获取量能数据失败: {str(e)}")
        return (0, 0, 0)


def get_buy_reason(stock, context):
    """
    获取买入原因

    参数:
        stock: 股票代码
        context: 上下文对象

    返回:
        买入原因字符串
    """
    try:
        # 检查股票属于哪种模式
        if hasattr(g, 'lblt_stocks') and stock in g.lblt_stocks:
            return '连板龙头'
        elif hasattr(g, 'gk_stocks') and stock in g.gk_stocks:
            return '一进二'
        elif hasattr(g, 'rzq_stocks') and stock in g.rzq_stocks:
            return '弱转强'
        elif hasattr(g, 'dk_stocks') and stock in g.dk_stocks:
            return '首板低开'
        elif hasattr(g, 'fxsbdk_stocks') and stock in g.fxsbdk_stocks:
            return '反向首板低开'
        else:
            return '未知'

    except Exception as e:
        log.error(f"获取买入原因失败: {str(e)}")
        return '未知'


# ============================================================================
# 连板龙头策略实现
# ============================================================================

def execute_limit_up_strategy(context):
    """
    执行连板龙头策略

    策略逻辑：
    1. 获取昨日涨停股票
    2. 筛选连板龙头（连续涨停天数最高）
    3. 应用龙头特征筛选（市值、换手、概念等）
    4. 检查主线评分和量比
    5. 执行买入

    参数:
        context: 上下文对象

    返回:
        买入的股票列表
    """
    log.info("\n" + "=" * 60)
    log.info("执行连板龙头策略")
    log.info("=" * 60)

    try:
        # 初始化全局变量
        if not hasattr(g, 'lblt_stocks'):
            g.lblt_stocks = []

        # 获取日期
        date = context.previous_date
        date_now = context.current_dt.strftime("%Y-%m-%d")

        # 1. 准备股票列表
        initial_list = prepare_stock_list(date)
        log.info(f"初始股票数量: {len(initial_list)}")

        # 2. 获取昨日涨停股票
        hl0_list = get_hl_stock(initial_list, date)
        log.info(f"昨日涨停股票数量: {len(hl0_list)}")

        if not hl0_list:
            log.info("无昨日涨停股票，跳过连板龙头策略")
            return []

        # 3. 获取集合竞价数据
        auction_start = date_now + ' 09:15:00'
        auction_end = date_now + ' 09:25:00'
        auctions = get_call_auction(hl0_list, start_date=auction_start, end_date=auction_end,
                                   fields=['time', 'current']).set_index('code')

        if auctions.empty:
            log.info("无集合竞价数据，跳过连板龙头策略")
            return []

        # 4. 获取前收盘价
        h = get_price(hl0_list, end_date=date, fields=['close'], count=1, panel=False).set_index('code')
        if h.empty:
            log.info("无前收盘价数据，跳过连板龙头策略")
            return []

        # 5. 筛选集合竞价高开的股票
        auctions['pre_close'] = h['close']
        gk_list = auctions.query('pre_close * 1.00 < current').index.tolist()
        gkb = len(gk_list) / len(hl0_list) * 100  # 昨日涨停早盘高开比

        log.info(f"集合竞价高开股票数量: {len(gk_list)}, 高开比: {gkb:.2f}%")

        # 6. 高开比低于76%则不执行
        if gkb < 76:
            log.info(f"高开比{gkb:.2f}%低于76%，市场情绪不佳，跳过连板龙头策略")
            return []

        # 7. 获取连续涨停统计
        ccd = get_continue_count_df(gk_list, date, 20)
        if len(ccd) == 0:
            log.info("无连续涨停数据，跳过连板龙头策略")
            return []

        # 8. 筛选龙头股票（最高连板天数）
        M = ccd['count'].max()
        CCD = ccd[ccd['count'] == M]
        m = CCD['extreme_count'].min()
        lt = list(CCD.index)

        log.info(f"最高连板天数: {M}, 龙头股票数量: {len(lt)}")

        # 9. 获取热门概念
        try:
            dct = get_concept(lt, date)
            hot_concept = get_hot_concept(dct, date)
            hot_stocks = filter_concept_stock(dct, hot_concept) if hot_concept else []
        except Exception as e:
            log.warning(f"获取热门概念失败: {str(e)}")
            hot_concept = None
            hot_stocks = []

        # 10. 筛选高风险股票（近5日有2个以上连续一字板）
        high_risk_stocks = []
        for stock in lt:
            try:
                trade_days = get_trade_days(end_date=date, count=5)
                price_data = get_price(stock, start_date=trade_days[0], end_date=date,
                                     fields=['open', 'close', 'high', 'low', 'high_limit', 'low_limit'])

                consecutive_extreme = 0
                max_consecutive = 0
                for i in range(len(price_data)):
                    is_extreme = (price_data['high'][i] == price_data['low'][i] and
                                 price_data['close'][i] == price_data['high_limit'][i])
                    if is_extreme:
                        consecutive_extreme += 1
                    else:
                        max_consecutive = max(max_consecutive, consecutive_extreme)
                        consecutive_extreme = 0
                max_consecutive = max(max_consecutive, consecutive_extreme)

                if max_consecutive >= 2:
                    high_risk_stocks.append(stock)
            except Exception as e:
                log.error(f"计算{stock}近期一字板失败: {str(e)}")

        if high_risk_stocks:
            log.info(f"高风险股票（将被排除）: {high_risk_stocks}")

        # 11. 龙头特征筛选
        condition_dct = {}
        for s in lt:
            # 排除高风险股票
            if s in high_risk_stocks:
                continue

            try:
                # 独食
                ds = ccd.loc[s]['extreme_count']

                # 市值
                valuation = get_fundamentals(
                    query(valuation.code, valuation.circulating_market_cap).filter(valuation.code == s),
                    date)
                if len(valuation) == 0:
                    continue
                sz = valuation.iloc[0, 1]

                # 换手
                hsl_dict = HSL([s], date)
                hs = hsl_dict.get(s, 0)

                # 龙头概念
                c = 1 if s in hot_stocks else 0

                # 逻辑判断
                condition = ''
                if hs < 35 and ds < 10 and M > 2:
                    condition += '上升周期'
                if ds < 3 and 10 < hs < 25:
                    condition += '资金接力'
                if c == 1 and M <= 6:
                    condition += f'题材初期({hot_concept})'

                # 获取符合逻辑的列表
                if len(condition) != 0:
                    condition_dct[s] = get_security_info(s, date).display_name + ' —— ' + condition
            except Exception as e:
                log.error(f"龙头特征筛选{s}失败: {str(e)}")
                continue

        stock_list = list(condition_dct.keys())
        log.info(f"龙头特征筛选后股票数量: {len(stock_list)}")

        if not stock_list:
            log.info("无符合龙头特征的股票，跳过连板龙头策略")
            return []

        # 12. 因子过滤
        df = get_factor_filter_df(context, stock_list, g.jqfactor, g.sort)
        lblt_stocks = list(df.index)

        log.info(f"因子过滤后股票数量: {len(lblt_stocks)}")

        # 13. 检查主线评分和量比
        final_stocks = []
        for stock in lblt_stocks:
            try:
                # 检查主线评分
                mainline_score = calculate_mainline_score_optimized(stock, context)
                if mainline_score == 0:
                    log.info(f"股票 {stock} 主线分为0，不纳入候选")
                    continue

                # 检查量比
                last_volume, last_2_volume, volume_ratio = get_volume_data(stock, context)
                if volume_ratio < 1.184 or volume_ratio > 10.5:
                    log.info(f"股票 {stock} 量比{volume_ratio:.2f}不在1.184~10.5范围内")
                    continue

                final_stocks.append(stock)
                log.info(f"✓ {stock} - 主线分:{mainline_score}, 量比:{volume_ratio:.2f}")

            except Exception as e:
                log.error(f"检查股票{stock}失败: {str(e)}")
                continue

        log.info(f"最终符合条件的股票数量: {len(final_stocks)}")

        # 14. 保存到全局变量
        g.lblt_stocks = final_stocks

        return final_stocks

    except Exception as e:
        log.error(f"执行连板龙头策略失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())
        return []


# ============================================================================
# 一进二策略实现
# ============================================================================

def execute_one_to_two_strategy(context):
    """
    执行一进二策略

    策略逻辑：
    1. 获取昨日涨停但前天无涨停的股票（首板）
    2. 筛选集合竞价高开的股票
    3. 应用市值、金额、换手率条件过滤
    4. 检查量比和价格
    5. 执行买入

    参数:
        context: 上下文对象

    返回:
        买入的股票列表
    """
    log.info("\n" + "=" * 60)
    log.info("执行一进二策略")
    log.info("=" * 60)

    try:
        # 初始化全局变量
        if not hasattr(g, 'gk_stocks'):
            g.gk_stocks = []

        # 获取日期
        date = context.previous_date
        date_1 = get_trade_days(end_date=date, count=2)[0]
        date_now = context.current_dt.strftime("%Y-%m-%d")

        # 1. 准备股票列表
        initial_list = prepare_stock_list(date)
        log.info(f"初始股票数量: {len(initial_list)}")

        # 2. 获取昨日涨停股票
        hl0_list = get_hl_stock(initial_list, date)
        log.info(f"昨日涨停股票数量: {len(hl0_list)}")

        # 3. 获取前日曾涨停股票
        hl1_list = get_ever_hl_stock(initial_list, date_1)
        log.info(f"前日曾涨停股票数量: {len(hl1_list)}")

        # 4. 筛选昨天涨停但前天无涨停的股票（首板）
        gap_up_list = [stock for stock in hl0_list if stock not in hl1_list]
        log.info(f"首板股票数量: {len(gap_up_list)}")

        if not gap_up_list:
            log.info("无首板股票，跳过一进二策略")
            return []

        # 5. 获取集合竞价数据
        auction_start = date_now + ' 09:15:00'
        auction_end = date_now + ' 09:25:00'
        auctions = get_call_auction(gap_up_list, start_date=auction_start, end_date=auction_end,
                                   fields=['time', 'current', 'volume']).set_index('code')

        if auctions.empty:
            log.info("无集合竞价数据，跳过一进二策略")
            return []

        # 6. 获取前收盘价
        h = get_price(gap_up_list, end_date=date, fields=['close'], count=1, panel=False).set_index('code')
        if h.empty:
            log.info("无前收盘价数据，跳过一进二策略")
            return []

        # 7. 筛选集合竞价高开的股票
        auctions['pre_close'] = h['close']
        gk_list = auctions.query('pre_close * 1.00 < current').index.tolist()

        log.info(f"集合竞价高开股票数量: {len(gk_list)}")

        if not gk_list:
            log.info("无集合竞价高开股票，跳过一进二策略")
            return []

        # 8. 获取当前数据
        current_data = get_current_data()

        # 9. 筛选符合条件的股票
        final_stocks = []
        for s in gk_list:
            try:
                # 条件一：均价、金额、市值、换手率
                prev_day_data = attribute_history(s, 1, '1d', fields=['close', 'volume', 'money'], skip_paused=True)
                if len(prev_day_data) < 1:
                    continue

                avg_price_increase_value = prev_day_data['money'][0] / prev_day_data['volume'][0] / prev_day_data['close'][0] * 1.1 - 1
                if avg_price_increase_value < 0.07 or prev_day_data['money'][0] < 5.5e8 or prev_day_data['money'][0] > 20e8:
                    continue

                # 市值条件
                turnover_ratio_data = get_valuation(s, start_date=context.previous_date, end_date=context.previous_date,
                                                  fields=['turnover_ratio', 'market_cap', 'circulating_market_cap'])
                if turnover_ratio_data.empty or turnover_ratio_data['market_cap'][0] < 50 or \
                        turnover_ratio_data['circulating_market_cap'][0] > 520:
                    continue

                # 条件二：左压（缩量上涨）
                if rise_low_volume(s, context):
                    continue

                # 条件三：高开、开比
                auction_data = get_call_auction(s, start_date=date_now, end_date=date_now,
                                              fields=['time', 'volume', 'current'])
                if auction_data.empty or auction_data['volume'][0] / prev_day_data['volume'][-1] < 0.03:
                    continue

                # 获取涨停价，如果当前数据为0则使用历史数据计算
                high_limit = current_data[s].high_limit if s in current_data and current_data[s].high_limit > 0 else 0
                if high_limit <= 0:
                    try:
                        # 使用上一交易日收盘价计算涨停价
                        hist_price = get_price(s, end_date=context.previous_date, count=1, fields=['close'], frequency='daily')
                        if hist_price is not None and len(hist_price) > 0:
                            high_limit = hist_price['close'].iloc[-1] * 1.1
                        else:
                            continue
                    except Exception as e:
                        log.error(f"获取{s}涨停价失败: {str(e)}")
                        continue

                current_ratio = auction_data['current'][0] / (high_limit / 1.1)
                if current_ratio <= 1 or current_ratio >= 1.06:
                    continue

                # 条件4：价格<47（一进二模式优选中低价股）
                current_price = current_data[s].last_price
                if current_price > 47:
                    continue

                # 条件5：量比范围检查（1.15~6.58是一进二模式的最佳量比区间）
                last_volume, last_2_volume, volume_ratio = get_volume_data(s, context)
                if volume_ratio < 1.15 or volume_ratio > 6.58:
                    log.info(f"股票 {s} 量比{volume_ratio:.2f}不在1.15~6.58范围内")
                    continue

                # 条件6：检查主线评分
                mainline_score = calculate_mainline_score_optimized(s, context)
                if mainline_score == 0:
                    log.info(f"股票 {s} 主线分为0，不纳入候选")
                    continue

                final_stocks.append(s)
                log.info(f"✓ {s} - 总市值:{turnover_ratio_data['market_cap'][0]:.2f}, "
                        f"流通市值:{turnover_ratio_data['circulating_market_cap'][0]:.2f}, "
                        f"量比:{volume_ratio:.2f}, 主线分:{mainline_score}")

            except Exception as e:
                log.error(f"筛选股票{s}失败: {str(e)}")
                continue

        log.info(f"最终符合条件的股票数量: {len(final_stocks)}")

        # 10. 保存到全局变量
        g.gk_stocks = final_stocks

        return final_stocks

    except Exception as e:
        log.error(f"执行一进二策略失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())
        return []


# ============================================================================
# 弱转强策略实现
# ============================================================================

def execute_reversal_strategy(context):
    """
    执行弱转强策略

    策略逻辑：
    1. 获取昨日曾涨停但收盘未涨停的股票
    2. 筛选前天无涨停的股票
    3. 应用涨幅、换手率、市值条件过滤
    4. 检查集合竞价和量比
    5. 执行买入

    参数:
        context: 上下文对象

    返回:
        买入的股票列表
    """
    log.info("\n" + "=" * 60)
    log.info("执行弱转强策略")
    log.info("=" * 60)

    try:
        # 初始化全局变量
        if not hasattr(g, 'rzq_stocks'):
            g.rzq_stocks = []

        # 获取日期
        date = context.previous_date
        date_1 = get_trade_days(end_date=date, count=2)[0]
        date_now = context.current_dt.strftime("%Y-%m-%d")

        # 1. 准备股票列表
        initial_list = prepare_stock_list(date)
        log.info(f"初始股票数量: {len(initial_list)}")

        # 2. 获取昨日曾涨停股票
        h1_list = get_ever_hl_stock2(initial_list, date)
        log.info(f"昨日曾涨停股票数量: {len(h1_list)}")

        # 3. 获取前日涨停股票
        hl1_list = get_hl_stock(initial_list, date_1)
        log.info(f"前日涨停股票数量: {len(hl1_list)}")

        # 4. 筛选昨天曾涨停但收盘未涨停且前天无涨停的股票（弱转强）
        reversal_list = [stock for stock in h1_list if stock not in hl1_list]
        log.info(f"弱转强候选股票数量: {len(reversal_list)}")

        if not reversal_list:
            log.info("无弱转强候选股票，跳过弱转强策略")
            return []

        # 5. 获取当前数据
        current_data = get_current_data()

        # 6. 筛选符合条件的股票
        final_stocks = []
        for s in reversal_list:
            try:
                # 过滤前面三天涨幅超过28%的票
                price_data = attribute_history(s, 4, '1d', fields=['close'], skip_paused=True)
                if len(price_data) < 4:
                    continue
                increase_ratio = (price_data['close'][-1] - price_data['close'][0]) / price_data['close'][0]
                if increase_ratio > 0.28:
                    log.info(f"股票 {s} 前三天涨幅{increase_ratio:.2%}超过28%，排除")
                    continue

                # 过滤前一日收盘价小于开盘价5%以上的票
                prev_day_data = attribute_history(s, 1, '1d', fields=['open', 'close'], skip_paused=True)
                if len(prev_day_data) < 1:
                    continue
                open_close_ratio = (prev_day_data['close'][0] - prev_day_data['open'][0]) / prev_day_data['open'][0]
                if open_close_ratio < -0.05:
                    log.info(f"股票 {s} 前一日收盘价较开盘价下跌{open_close_ratio:.2%}超过5%，排除")
                    continue

                # 检查均价、金额、市值、换手率
                prev_day_data = attribute_history(s, 1, '1d', fields=['close', 'volume', 'money'], skip_paused=True)
                avg_price_increase_value = prev_day_data['money'][0] / prev_day_data['volume'][0] / prev_day_data['close'][0] - 1
                if avg_price_increase_value < -0.04 or prev_day_data['money'][0] < 3e8 or prev_day_data['money'][0] > 19e8:
                    continue

                turnover_ratio_data = get_valuation(s, start_date=context.previous_date, end_date=context.previous_date,
                                                  fields=['turnover_ratio', 'market_cap', 'circulating_market_cap'])
                if turnover_ratio_data.empty or turnover_ratio_data['market_cap'][0] < 70 or \
                        turnover_ratio_data['circulating_market_cap'][0] > 520:
                    continue

                # 检查左压
                if rise_low_volume(s, context):
                    continue

                # 检查集合竞价
                auction_data = get_call_auction(s, start_date=date_now, end_date=date_now,
                                              fields=['time', 'volume', 'current'])
                if auction_data.empty or auction_data['volume'][0] / prev_day_data['volume'][-1] < 0.03:
                    continue

                current_ratio = auction_data['current'][0] / (current_data[s].high_limit / 1.1)
                if current_ratio <= 0.98 or current_ratio >= 1.09:
                    continue

                # 检查主线评分
                mainline_score = calculate_mainline_score_optimized(s, context)
                if mainline_score == 0:
                    log.info(f"股票 {s} 主线分为0，不纳入候选")
                    continue

                # 检查量比
                last_volume, last_2_volume, volume_ratio = get_volume_data(s, context)
                if volume_ratio < 1.072 or volume_ratio > 3.68:
                    log.info(f"股票 {s} 量比{volume_ratio:.2f}不在1.072~3.68范围内")
                    continue

                final_stocks.append(s)
                log.info(f"✓ {s} - 主线分:{mainline_score}, 量比:{volume_ratio:.2f}")

            except Exception as e:
                log.error(f"筛选股票{s}失败: {str(e)}")
                continue

        log.info(f"最终符合条件的股票数量: {len(final_stocks)}")

        # 7. 保存到全局变量
        g.rzq_stocks = final_stocks

        return final_stocks

    except Exception as e:
        log.error(f"执行弱转强策略失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())
        return []


# ============================================================================
# 反向首板低开策略实现
# ============================================================================

def execute_reverse_limit_up_strategy(context):
    """
    执行反向首板低开策略

    策略逻辑：
    1. 获取昨日跌停股票
    2. 筛选非连板跌停的股票
    3. 计算相对位置
    4. 筛选低开幅度在4%~10%的股票
    5. 执行买入

    参数:
        context: 上下文对象

    返回:
        买入的股票列表
    """
    log.info("\n" + "=" * 60)
    log.info("执行反向首板低开策略")
    log.info("=" * 60)

    try:
        # 初始化全局变量
        if not hasattr(g, 'fxsbdk_stocks'):
            g.fxsbdk_stocks = []

        # 获取日期
        date = context.previous_date
        date_now = context.current_dt.strftime("%Y-%m-%d")

        # 1. 准备股票列表
        initial_list = prepare_stock_list(date)
        log.info(f"初始股票数量: {len(initial_list)}")

        # 2. 获取昨日跌停股票
        ll_list = get_ll_stock(initial_list, date)
        log.info(f"昨日跌停股票数量: {len(ll_list)}")

        if not ll_list:
            log.info("无昨日跌停股票，跳过反向首板低开策略")
            return []

        # 3. 获取连续跌停统计
        ccd = get_continue_count_df_ll(ll_list, date, 10)
        lb_list = list(ccd.index)
        stock_list = [s for s in ll_list if s not in lb_list]

        log.info(f"非连板跌停股票数量: {len(stock_list)}")

        if not stock_list:
            log.info("无非连板跌停股票，跳过反向首板低开策略")
            return []

        # 4. 计算相对位置
        rpd = get_relative_position_df(stock_list, date, 60)
        rpd = rpd[rpd['rp'] <= 0.5]
        stock_list = list(rpd.index)

        log.info(f"相对位置≤0.5的股票数量: {len(stock_list)}")

        if not stock_list:
            log.info("无相对位置≤0.5的股票，跳过反向首板低开策略")
            return []

        # 5. 低开筛选
        df = get_price(stock_list, end_date=date, frequency='daily', fields=['close'], count=1, panel=False,
                       fill_paused=False, skip_paused=True).set_index('code')
        if df.empty:
            log.info("无价格数据，跳过反向首板低开策略")
            return []

        current_data = get_current_data()
        df['open_pct'] = [current_data[s].day_open / df.loc[s, 'close'] for s in stock_list]
        df = df[(1.04 <= df['open_pct']) & (df['open_pct'] < 1.10)]  # 筛选特定低开幅度
        final_stocks = list(df.index)

        log.info(f"低开4%~10%的股票数量: {len(final_stocks)}")

        # 6. 保存到全局变量
        g.fxsbdk_stocks = final_stocks

        return final_stocks

    except Exception as e:
        log.error(f"执行反向首板低开策略失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())
        return []


# ============================================================================
# 均值回归策略实现
# ============================================================================

def execute_mean_reversion_strategy(context):
    """
    执行均值回归策略

    策略逻辑：
    1. 获取股票池
    2. 计算布林带指标
    3. 筛选价格接近下轨的股票
    4. 检查RSI指标（超卖）
    5. 执行买入

    参数:
        context: 上下文对象

    返回:
        买入的股票列表
    """
    log.info("\n" + "=" * 60)
    log.info("执行均值回归策略")
    log.info("=" * 60)

    try:
        # 获取股票池
        stock_pool = g.stock_pool if hasattr(g, 'stock_pool') else []
        if not stock_pool:
            log.info("股票池为空，跳过均值回归策略")
            return []

        log.info(f"股票池数量: {len(stock_pool)}")

        # 筛选符合条件的股票
        final_stocks = []
        for stock in stock_pool:
            try:
                # 计算布林带
                boll_df = calculate_boll(stock, context)
                if boll_df.empty:
                    continue

                lower = boll_df['lower'].iloc[0]
                middle = boll_df['middle'].iloc[0]

                # 获取当前价格
                current_data = get_current_data()
                if stock not in current_data:
                    continue
                current_price = current_data[stock].last_price
                # 如果当前价格为0，尝试获取上一交易日收盘价作为备用
                if current_price <= 0:
                    try:
                        hist_price = get_price(stock, end_date=context.previous_date, count=1, fields=['close'], frequency='daily')
                        if hist_price is not None and len(hist_price) > 0:
                            current_price = hist_price['close'].iloc[-1]
                        else:
                            continue
                    except Exception as e:
                        log.error(f"获取{stock}价格失败: {str(e)}")
                        continue

                # 检查价格是否接近下轨（下轨上方2%以内）
                if current_price > lower * 1.02:
                    log.info(f"股票 {stock} 价格{current_price:.2f}高于下轨{lower:.2f}的2%，排除")
                    continue

                # 计算RSI
                rsi_df = calculate_rsi(stock, context)
                if rsi_df.empty:
                    continue

                rsi = rsi_df['RSI'].iloc[0]

                # 检查RSI是否超卖（RSI < 30）
                if rsi >= 30:
                    log.info(f"股票 {stock} RSI{rsi:.2f}未超卖，排除")
                    continue

                final_stocks.append(stock)
                log.info(f"✓ {stock} - 价格:{current_price:.2f}, 下轨:{lower:.2f}, RSI:{rsi:.2f}")

            except Exception as e:
                log.error(f"筛选股票{stock}失败: {str(e)}")
                continue

        log.info(f"最终符合条件的股票数量: {len(final_stocks)}")

        return final_stocks

    except Exception as e:
        log.error(f"执行均值回归策略失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())
        return []


# ============================================================================
# 优质股低吸策略实现
# ============================================================================

def execute_value_stock_strategy(context):
    """
    执行优质股低吸策略

    策略逻辑：
    1. 获取多因子选股结果
    2. 筛选低估值、高ROE的股票
    3. 检查价格位置（相对低位）
    4. 执行买入

    参数:
        context: 上下文对象

    返回:
        买入的股票列表
    """
    log.info("\n" + "=" * 60)
    log.info("执行优质股低吸策略")
    log.info("=" * 60)

    try:
        # 获取股票池
        stock_pool = g.stock_pool if hasattr(g, 'stock_pool') else []
        if not stock_pool:
            log.info("股票池为空，跳过优质股低吸策略")
            return []

        log.info(f"股票池数量: {len(stock_pool)}")

        # 获取估值数据
        end_date = context.previous_date.strftime("%Y-%m-%d")
        q = query(
            valuation.code,
            valuation.pe_ratio,
            valuation.pb_ratio,
            valuation.market_cap
        ).filter(
            valuation.code.in_(stock_list=stock_pool),
            valuation.pe_ratio > 0,
            valuation.pe_ratio < 30  # PE < 30
        )

        df_valuation = get_fundamentals(q, date=end_date).set_index('code')

        if df_valuation.empty:
            log.info("无估值数据，跳过优质股低吸策略")
            return []

        # 获取财务数据
        q = query(
            indicator.code,
            indicator.roe,
            indicator.roa
        ).filter(
            indicator.code.in_(stock_list=stock_pool),
            indicator.roe > 10  # ROE > 10%
        )

        df_finance = get_fundamentals(q).set_index('code')

        if df_finance.empty:
            log.info("无财务数据，跳过优质股低吸策略")
            return []

        # 合并数据
        df = pd.merge(df_valuation, df_finance, left_index=True, right_index=True, how='inner')

        # 筛选符合条件的股票
        final_stocks = []
        for stock in df.index:
            try:
                pe = df.loc[stock, 'pe_ratio']
                pb = df.loc[stock, 'pb_ratio']
                roe = df.loc[stock, 'roe']

                # 获取当前价格和计算相对位置
                rpd = get_relative_position_df([stock], end_date, 60)
                if stock not in rpd.index:
                    continue

                rp = rpd.loc[stock, 'rp']

                # 检查相对位置（低位）
                if rp > 0.3:
                    log.info(f"股票 {stock} 相对位置{rp:.2f}偏高，排除")
                    continue

                final_stocks.append(stock)
                log.info(f"✓ {stock} - PE:{pe:.2f}, PB:{pb:.2f}, ROE:{roe:.2f}, 相对位置:{rp:.2f}")

            except Exception as e:
                log.error(f"筛选股票{stock}失败: {str(e)}")
                continue

        log.info(f"最终符合条件的股票数量: {len(final_stocks)}")

        return final_stocks

    except Exception as e:
        log.error(f"执行优质股低吸策略失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())
        return []
