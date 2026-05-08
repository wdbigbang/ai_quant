# -*- coding: utf-8 -*-
"""
聚宽多策略量化交易系统 v9.0.0

本策略将小市值波段策略（主策略）和ETF核心资产轮动策略（辅助策略）整合到统一框架中，
实现多策略互不干扰、资金池动态分配的统一框架。

策略信息：
- 主策略：小市值波段策略（min_cooldown_swing_strategy）
  原作者：wellfuture
  年化收益：57%
  核心逻辑：小市值选股、波段交易、冷静期机制、空仓月管理

- 辅助策略：ETF核心资产轮动策略（ETF_Core_Asset_Rotation_Strategy）
  原作者：MarioC / wywy1995
  年化收益：51.11%
  核心逻辑：基于动量因子在4只ETF之间轮动

版本信息：
- 版本号：v9.0.0
- 创建日期：2026-02-02
- 最后更新：2026-03-12
- 目标平台：聚宽JoinQuant（兼容QMT、PTrade）
- 代码行数：约6400行

核心功能（v9.0.0）：
✅ 资金池动态分配系统（四维度评分系统：收益率40%、胜率25%、风险25%、稳定性10%）
✅ 策略框架（StrategyManager、BaseStrategy、SwingStrategy、ETFRotationStrategy）
✅ 多策略标签系统（持仓归属管理、避免冲突）
✅ 全仓模式支持（用于测试单一策略效果）
✅ 空仓月策略（1月、4月空仓）
✅ 冷静期策略（3日连续跌幅-2%触发）

下一步重点：
- 聚宽模拟盘测试验证
- QMT/PTrade平台适配准备

参考文章：
- https://www.joinquant.com/post/60233（小市值波段策略）
- https://www.joinquant.com/post/49263（ETF核心资产轮动策略）
- https://www.joinquant.com/post/42673（ETF策略之核心资产轮动）
"""

# ============================================================================
# 1. 导入模块
# ============================================================================

# 1.1 Python标准库
import datetime as dt
from datetime import datetime, timedelta

# 1.2 第三方库
import pandas as pd
import numpy as np
from typing import Any, Optional, Union, Dict, List, Callable

# 1.3 聚宽平台API
from jqdata import *
from jqfactor import *
from jqlib.technical_analysis import *

# ============================================================================
# 注释：未来平台兼容性说明
# ============================================================================
# 以下API为聚宽平台特有，迁移到QMT/PTrade时需要替换：
#
# 数据获取类API：
# - get_price()           → QMT: get_market_data()
# - get_fundamentals()    → QMT: get_fundamentals()
# - get_current_data()    → QMT: get_full_tick()
# - get_trade_days()      → QMT: get_trade_days()
#
# 订单管理类API：
# - order()               → QMT: passorder()
# - order_value()         → QMT: passorder()按金额
# - order_target_value()  → QMT: passorder()目标市值
# - order_target()        → QMT: passorder()目标数量
#
# 技术分析类API：
# - jqlib.technical_analysis.* → QMT: 使用TA-Lib库
#
# 聚宽因子类API：
# - jqfactor.*            → QMT: 自行计算因子
# ============================================================================

# ============================================================================
# 1. 全局配置和常量定义
# ============================================================================

# 系统版本信息
SYSTEM_VERSION = "8.0.0"
STRATEGY_NAME = "多策略量化交易系统"

# 日志级别配置
LOG_LEVEL = {
    'system': 'error',
    'order': 'error',
    'strategy': 'debug'
}

# 基准指数
BENCHMARK = '000300.XSHG'  # 沪深300

# 交易时段映射（中文描述）
TIME_STATUS_MAP = {
    'pre_market': '盘前集合竞价',
    'morning': '上午交易',
    'lunch_break': '午休时段',
    'afternoon': '下午交易',
    'after_market': '盘后时段',
    'non_trading': '非交易时段'
}

# ============================================================================
# 2. 策略初始化函数
# ============================================================================

def initialize(context):
    """
    策略初始化函数
    
    功能说明：
    1. 设置基准指数和交易选项
    2. 设置滑点和交易成本（贴近实盘）
    3. 初始化全局变量（系统配置、策略管理器、标签系统等）
    4. 设置定时任务（盘前、盘中、盘后）
    5. 初始化策略实例
    """
    log.info(f"=" * 60)
    log.info(f"{STRATEGY_NAME} v{SYSTEM_VERSION} 初始化开始")
    log.info(f"=" * 60)
    
    # ==================== 2.1 设置基准指数和交易选项 ====================
    set_benchmark(BENCHMARK)
    log.info(f"基准指数设置: {BENCHMARK}")
    
    set_option('use_real_price', True)  # 使用真实价格
    set_option('avoid_future_data', True)  # 避免未来数据
    log.info("交易选项设置: use_real_price=True, avoid_future_data=True")
    
    # ==================== 2.2 设置滑点和交易成本（贴近实盘） ====================
    # 设置滑点 （股票0.2%，基金0.01%）
    set_slippage(FixedSlippage(0.002), type="stock")
    set_slippage(FixedSlippage(0.0001), type="fund")
    log.info("滑点设置: 股票0.2%, 基金0.01%")
    
    # 设置交易成本（按聚官认知费率）
    set_order_cost(
        OrderCost(
            open_tax=0,  # 买入无印花税
            close_tax=0.001,  # 卖出印花税0.1%
            open_commission=0.0003,  # 买入佣金0.03%
            close_commission=0.0003,  # 卖出佣金0.03%
            close_today_commission=0,  # 当日卖出无额外佣金
            min_commission=5  # 最低佣金5元
        ),
        type='stock'
    )
    log.info("交易成本设置: 印花税0.1%, 佣金0.03%, 最低5元")
    
    # 设置基金交易成本（ETF、LOF等）
    set_order_cost(
        OrderCost(
            open_tax=0,  # 买入无印花税
            close_tax=0,  # 卖出无印花税
            open_commission=0.0002,  # 买入佣金0.02%
            close_commission=0.0002,  # 卖出佣金0.02%
            close_today_commission=0,  # 当日卖出无额外佣金
            min_commission=5  # 最低佣金5元
        ),
        type='fund'
    )
    log.info("基金交易成本设置: 无印花税, 佣金0.02%, 最低5元")
    
    # 设置日志级别
    log.set_level('system', LOG_LEVEL['system'])
    log.set_level('order', LOG_LEVEL['order'])
    log.set_level('strategy', LOG_LEVEL['strategy'])
    log.info(f"日志级别设置: system={LOG_LEVEL['system']}, order={LOG_LEVEL['order']}, strategy={LOG_LEVEL['strategy']}")
    
    # ==================== 2.3 初始化全局变量 ====================
    _init_global_variables(context)
    
    # ==================== 2.3.5 初始资金池分配 ====================
    # 在策略注册后立即进行初始资金池分配（使用初始比例）
    if hasattr(g, 'strategy_manager') and hasattr(g.strategy_manager, 'strategies'):
        total_capital = context.portfolio.starting_cash
        log.info(f"初始资金池分配: 总资金 {total_capital:.2f}元")
        
        # 检查是否开启全仓模式
        if getattr(g, 'enable_full_ratio_mode', False) and hasattr(g, 'full_ratio_strategy_id'):
            full_ratio_strategy_id = g.full_ratio_strategy_id
            log.info(f"检测到全仓模式配置: 全仓策略={full_ratio_strategy_id}")
            
            # 全仓模式：只分配给指定的全仓策略
            for strategy_id in g.strategy_manager.strategies.keys():
                pool = g.strategy_manager.capital_pools[strategy_id]
                if strategy_id == full_ratio_strategy_id:
                    pool['ratio'] = 1.0
                    pool['amount'] = total_capital
                    log.info(f"  {strategy_id}: {pool['ratio']:.2%} ({pool['amount']:.2f}元) [全仓模式]")
                else:
                    pool['ratio'] = 0.0
                    pool['amount'] = 0.0
                    log.info(f"  {strategy_id}: {pool['ratio']:.2%} ({pool['amount']:.2f}元) [全仓模式下禁用]")
        else:
            # 默认模式：计算初始比例总和并归一化
            total_ratio = sum(
                g.strategy_manager.capital_pools.get(sid, {}).get('ratio', 0)
                for sid in g.strategy_manager.strategies.keys()
            )
            
            # 归一化比例
            if total_ratio > 0:
                for strategy_id in g.strategy_manager.strategies.keys():
                    pool = g.strategy_manager.capital_pools[strategy_id]
                    normalized_ratio = pool['ratio'] / total_ratio
                    pool['ratio'] = normalized_ratio
                    pool['amount'] = total_capital * normalized_ratio
                    log.info(f"  {strategy_id}: {normalized_ratio:.2%} ({pool['amount']:.2f}元)")
            else:
                log.warning("所有策略的初始比例总和为0，无法分配资金池")
    
    # ==================== 2.3.5 记录初始资金 ====================
    g.initial_capital = context.portfolio.starting_cash  # 记录初始资金
    log.info(f"初始资金: {g.initial_capital:.2f}")
    
    # ==================== 2.4 设置定时任务 ====================
    _setup_scheduled_tasks(context)
    
    # ==================== 2.5 策略实例初始化完成 ====================
    # 策略实例已在 _init_global_variables 中完成初始化
    # - test_strategy_1: SwingStrategy（小市值波段策略，主策略）
    # - test_strategy_2: TestStrategy（ETF轮动策略，辅助策略）
    log.info("策略实例初始化完成: test_strategy_1（SwingStrategy主策略）+ test_strategy_2（ETF轮动辅助策略）")
    
    log.info(f"=" * 60)
    log.info(f"{STRATEGY_NAME} 初始化完成")
    log.info(f"=" * 60)


def _init_global_variables(context):
    """
    初始化全局变量
    
    包括：
    - 系统配置
    - 总控决策模块
    - 策略标签系统
    - 交易统计
    - 调试信息栏
    """
    # ========== 系统配置 ==========
    g.system_config = {
        'platform': 'joinquant',
        'target_platforms': ['joinquant', 'qmt', 'ptrade'],
        'version': SYSTEM_VERSION
    }
    
    # ========== 总控决策模块 ==========
    g.strategy_manager = {
        'strategies': {},  # 策略实例字典
        'capital_pools': {},  # 各策略资金池
        'priority_order': [],  # 策略优先级顺序
        'last_allocation_date': None,  # 上次资金分配日期
        'monthly_adjustment_day': 1  # 每月几号调整资金
    }
    
    # ========== 策略标签系统 ==========
    g.strategy_tags = {}  # {stock_code: strategy_id}
    g.strategy_positions = {}  # {strategy_id: [stock_codes]}
    
    # ========== 交易统计 ==========
    g.trade_stats = {
        'daily_returns': [],  # 每日收益
        'position_stats': {},  # 持仓统计
        'market_stats': {},  # 市场统计
        'trade_details': [],  # 交易明细
        'strategy_performance': {}  # 各策略绩效统计
    }
    
    g.test_mode = True  # 保留此变量，因为代码中多处使用
    g.test_priority_allocation = True  # 保留此变量，因为代码中多处使用
    
    # ========== 策略注册开关配置（统一管理所有策略的注册状态） ==========
    g.strategy_registration = {
        'test_1': True,      # SwingStrategy（小市值波段策略）
        'test_2': True       # ETFRotationStrategy（ETF轮动策略）
    }
    
    # 输出策略注册状态
    enabled_strategies = [k for k, v in g.strategy_registration.items() if v]
    log.info(f"策略注册开关: {enabled_strategies}")
    
    # ========== 全仓模式配置（用于测试单一策略效果） ==========
    g.enable_full_ratio_mode = False  # 是否开启全仓模式（默认关闭）
    g.full_ratio_strategy_id = 'test_strategy_2'  # 使用全仓模式的策略ID test_strategy_1 test_strategy_2
    
    log.info(f"全仓模式配置: enable={g.enable_full_ratio_mode}, strategy={g.full_ratio_strategy_id}")
    
    # ========== 市场状态 ==========
    g.market_state = {
        'is_empty': False,  # 是否空仓
        'market_trend': 'flat',  # 市场趋势: up, down, strong_up, flat
        'last_trend_update': None  # 上次趋势更新时间
    }
    
    # ========== 总控决策管理器实例 ==========
    g.strategy_manager = StrategyManager()
    log.info("总控决策管理器 StrategyManager 实例已创建")
    
    # ========== 注册策略（根据g.strategy_registration开关） ==========
    # 注意：所有策略的注册都统一通过g.strategy_registration字典控制
    
    # 1. 注册测试策略1（test_strategy_1）- 当前使用SwingStrategy进行调试
    if g.test_mode and g.strategy_registration.get('test_1', False):
        # 创建小市值波段策略实例
        test_strategy_1 = SwingStrategy(strategy_id='test_strategy_1')
        
        # 根据配置决定是否开启全仓模式
        if getattr(g, 'enable_full_ratio_mode', False) and g.full_ratio_strategy_id == 'test_strategy_1':
            # 全仓模式：使用100%资金池
            initial_ratio = 1.0
            full_ratio_mode = True
            log.info(f"【配置】test_strategy_1 开启全仓模式，将使用100%资金池")
        else:
            # 默认模式：使用50%资金池
            initial_ratio = 0.5
            full_ratio_mode = False
        
        # 注册测试策略1到StrategyManager
        g.strategy_manager.register_strategy(
            strategy_id='test_strategy_1',
            strategy_instance=test_strategy_1,
            initial_ratio=initial_ratio,
            full_ratio_mode=full_ratio_mode
        )
        
        # 将策略实例保存到全局变量，方便后续调用
        g.test_strategy_1 = test_strategy_1
        if full_ratio_mode:
            log.info(f"【阶段六】测试策略1 test_strategy_1 已注册到StrategyManager（使用SwingStrategy，全仓模式100%）")
        else:
            log.info(f"【阶段六】测试策略1 test_strategy_1 已注册到StrategyManager（使用SwingStrategy，初始比例70%）")
    
    # 2. 注册测试策略2（test_strategy_2）- ETF轮动策略
    if g.test_mode and g.strategy_registration.get('test_2', False):
        # 创建ETF核心资产轮动策略实例（使用固定ETF池，与原始策略对齐）
        etf_params = {
            'auto_fetch_etf_pool': False,  # 禁用自动获取ETF池，使用固定ETF池
            'auto_fetch_num': 10,  # 目标获取10只ETF（已禁用，保留参数）
            'auto_fetch_min_days': 480,  # 最小上市天数480天（已禁用，保留参数）
        }
        etf_rotation_strategy = ETFRotationStrategy(strategy_id='test_strategy_2', params=etf_params)
        
        # 根据配置决定是否开启全仓模式
        if getattr(g, 'enable_full_ratio_mode', False) and g.full_ratio_strategy_id == 'test_strategy_2':
            # 全仓模式：使用100%资金池
            initial_ratio = 1.0
            full_ratio_mode = True
            log.info(f"【配置】test_strategy_2 开启全仓模式，将使用100%资金池")
        else:
            # 默认模式：使用50%资金池
            initial_ratio = 0.5
            full_ratio_mode = False
        
        # 注册ETF轮动策略到StrategyManager
        g.strategy_manager.register_strategy(
            strategy_id='test_strategy_2',
            strategy_instance=etf_rotation_strategy,
            initial_ratio=initial_ratio,
            full_ratio_mode=full_ratio_mode
        )
        
        # 将ETF轮动策略实例保存到全局变量，方便后续调用
        g.test_strategy_2 = etf_rotation_strategy
        if full_ratio_mode:
            log.info(f"【阶段八】测试策略2 test_strategy_2 已注册到StrategyManager（使用ETFRotationStrategy，全仓模式100%，自动获取ETF池）")
        else:
            log.info(f"【阶段八】测试策略2 test_strategy_2 已注册到StrategyManager（使用ETFRotationStrategy，初始比例30%，自动获取ETF池）")
    
    log.info("全局变量初始化完成")


def _setup_scheduled_tasks(context):
    """
    设置定时任务
    
    包括：
    - 盘前任务（09:25）
    - 盘中任务（买卖、风控）
    - 盘后任务（15:00、15:05）
    """
    # ==================== 盘前任务 ====================
    run_daily(before_trading_start, '09:25')
    log.info("定时任务设置: before_trading_start 09:25")
    
    # ==================== 主策略买卖任务（SwingStrategy - 小市值波段策略） ====================
    # 已在 _setup_scheduled_tasks 中启用
    # 09:31 买入，14:49 卖出
    # 注意：此处不再单独设置，已在下面通过 test_strategy_1 统一注册
    
    # ==================== 辅助策略买卖任务（test_strategy_2 - ETF轮动策略） ====================
    # 【阶段八】已通过 etf_rotation_trade 定时任务实现（每日09:30执行）
    # 注意：ETF轮动策略使用ETFRotationStrategy类，通过execute_trade方法执行交易逻辑
    log.info("定时任务设置: ETF轮动策略买卖任务（已通过etf_rotation_trade定时任务实现，每日09:30）")
    
    # ==================== ETF轮动策略交易任务（test_strategy_2 - ETFRotationStrategy） ====================
    # 【阶段八】每日09:35执行ETF轮动策略交易逻辑
    # - 计算动量因子并获取ETF排名
    # - 执行买卖操作（持仓1只ETF，全仓或空仓）
    run_daily(etf_rotation_trade, '09:35')
    log.info("定时任务设置: etf_rotation_trade 09:35（每日执行ETF轮动策略）")
    
    # ==================== 测试买卖任务 ====================
    # 【测试逻辑】简化版：每周最后一个交易日10:35执行
    # ==================== SwingStrategy买卖任务（小市值波段策略） ====================
    # 09:31 买入，14:49 卖出
    if g.test_mode and g.strategy_registration.get('test_1', False) and hasattr(g, 'test_strategy_1'):
        run_daily(swing_strategy_buy, '09:31')
        log.info("定时任务设置: swing_strategy_buy 09:31（小市值波段策略买入）")
        
        run_daily(swing_strategy_sell, '14:49')
        log.info("定时任务设置: swing_strategy_sell 14:49（小市值波段策略卖出）")
    else:
        log.info("定时任务设置: SwingStrategy买卖任务（待策略注册后启用）")
    
    # ==================== 分钟级风控任务（SwingStrategy） ====================
    # 启用分钟级风控任务
    if g.test_mode and g.strategy_registration.get('test_1', False) and hasattr(g, 'test_strategy_1'):
        for hour in range(9, 15):
            for minute in range(0, 60):
                time_str = f"{hour:02d}:{minute:02d}"
                # 交易时段：上午09:32-11:30，下午13:00-14:54
                # 每10分钟执行一次：32、42、52（上午）；00、10、20、30、40（下午）
                if ('09:31' < time_str < '11:30') or ('13:00' < time_str < '14:54'):
                    if minute % 10 == 0 or (hour == 9 and minute == 32):
                        run_daily(swing_strategy_interval_control, time=time_str)
        log.info("定时任务设置: swing_strategy_interval_control 每10分钟执行（小市值波段策略分钟风控）")
    else:
        log.info("定时任务设置: SwingStrategy分钟级风控任务（待策略注册后启用）")
    
    # ==================== 冷静期检查任务 ====================
    # 启用组合跌幅监控任务
    if g.test_mode and g.strategy_registration.get('test_1', False) and hasattr(g, 'test_strategy_1'):
        run_daily(swing_strategy_portfolio_monitor, '09:30')
        log.info("定时任务设置: swing_strategy_portfolio_monitor 09:30（小市值波段策略组合跌幅监控）")
    else:
        log.info("定时任务设置: SwingStrategy组合跌幅监控任务（待策略注册后启用）")
    
    # ==================== 盘后任务 ====================
    run_daily(after_trading_end, '15:30')
    log.info("定时任务设置: after_trading_end 15:30")
    
    run_daily(log_daily_trades, '15:55')
    log.info("定时任务设置: log_daily_trades 15:55")
    
    log.info("定时任务设置完成")


def log_daily_trades(context):
    """
    记录每日交易日志
    
    功能说明：
    1. 统计当日交易情况
    2. 计算总体盈亏
    3. 输出详细交易记录
    4. 更新交易统计到全局变量
    """
    try:
        if not hasattr(g, 'today_trades') or not g.today_trades:
            return

        log.info("\n==== 今日交易总结 ====")
        
        # 过滤掉None值（交易失败的记录）
        valid_trades = [trade for trade in g.today_trades if trade is not None]
        
        if not valid_trades:
            log.info("今日无有效交易记录")
            return
        
        # 统计交易情况
        total_trades = len(valid_trades)
        buy_trades = [trade for trade in valid_trades if trade.get('action') == '买入']
        sell_trades = [trade for trade in valid_trades if trade.get('action') == '卖出']
        
        log.info(f"总交易数: {total_trades}")
        log.info(f"买入交易: {len(buy_trades)}")
        log.info(f"卖出交易: {len(sell_trades)}")
        
        # 计算总体盈亏（基于卖出交易）
        if sell_trades:
            total_profit = sum(trade.get('profit', 0) for trade in sell_trades)
            total_profit_pct = sum(trade.get('profit_pct', 0) for trade in sell_trades) / len(sell_trades)
            log.info(f"总盈亏: {total_profit:.2f}")
            log.info(f"平均盈亏: {total_profit_pct:.2%}")
            
            # 统计盈利和亏损交易
            profit_trades = [t for t in sell_trades if t.get('profit', 0) > 0]
            loss_trades = [t for t in sell_trades if t.get('profit', 0) <= 0]
            win_rate = len(profit_trades) / len(sell_trades) if sell_trades else 0
            log.info(f"盈利交易: {len(profit_trades)}, 亏损交易: {len(loss_trades)}, 胜率: {win_rate:.2%}")
        
        # 按策略分组统计
        if hasattr(g, 'strategy_tags'):
            strategy_trades = {}
            for trade in valid_trades:  # 使用valid_trades而不是g.today_trades
                strategy_id = trade.get('strategy_id', 'unknown')
                if strategy_id not in strategy_trades:
                    strategy_trades[strategy_id] = []
                strategy_trades[strategy_id].append(trade)
            
            if strategy_trades:
                log.info(f"\n【按策略统计】")
                for strategy_id, trades in strategy_trades.items():
                    strategy_buys = len([t for t in trades if t['action'] == '买入'])
                    strategy_sells = len([t for t in trades if t['action'] == '卖出'])
                    log.info(f"  {strategy_id}: 买入{strategy_buys}次, 卖出{strategy_sells}次")
        
        # 详细交易记录
        log.info(f"\n【交易明细】")
        for trade in g.today_trades:
            stock_code = trade.get('stock', '')
            action = trade['action']
            price = trade.get('price', 0)
            amount = trade.get('amount', 0)
            reason = trade.get('reason', '无')
            strategy_id = trade.get('strategy_id', 'unknown')
            
            if action == '卖出':
                profit = trade.get('profit', 0)
                profit_pct = trade.get('profit_pct', 0)
                log.info(f"{stock_code} - {action} - 价格: {price:.2f} - 数量: {amount:.0f} - "
                       f"盈亏: {profit:.2f} ({profit_pct:.2%}) - 原因: {reason} - 策略: {strategy_id}")
            else:
                log.info(f"{stock_code} - {action} - 价格: {price:.2f} - 数量: {amount:.0f} - "
                       f"原因: {reason} - 策略: {strategy_id}")
        
        log.info("==== 交易总结结束 ====\n")
        
        # 将交易记录保存到全局统计中
        g.trade_stats['trade_details'].extend(g.today_trades)
        
        # 重置今日交易记录
        g.today_trades = []
    
    except Exception as e:
        log.error(f"记录每日交易日志失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())


# ============================================================================
# 3. 策略生命周期函数
# ============================================================================

def before_trading_start(context):
    """
    每日盘前准备函数
    功能说明：
    1. 清空当日变量
    2. 获取市场数据（大盘、涨跌停统计等）
    3. 检查空仓条件
    4. 检查冷静期状态
    5. 调用各策略的盘前准备函数（待后续任务完成）
    """
    # ==================== 3.1 清空当日变量 ====================
    _clear_daily_variables(context)
    # ==================== 3.2 获取市场数据 ====================
    _get_market_data(context)
    # ==================== 3.3 检查空仓条件 ====================
    _check_empty_position_condition(context)
    # ==================== 3.4 检查冷静期状态 ====================
    _check_cooldown_status(context)
    # ==================== 3.5 市场趋势分析与策略优先级更新 ====================
    if g.test_mode and g.test_priority_allocation and hasattr(g, 'strategy_manager'):
        try:
            # 分析市场趋势
            market_trend_info = g.strategy_manager.analyze_market_trend(context)
            # 根据市场趋势更新策略优先级
            if market_trend_info and 'trend' in market_trend_info:
                current_trend = market_trend_info['trend']
                g.strategy_manager.update_strategy_priority(current_trend)
                # ==================== 3.5.1 根据优先级调整资金池分配 ====================
                _check_capital_pool_adjustment(context)
        except Exception as e:
            log.error(f"市场趋势分析或策略优先级更新失败: {str(e)}")
    
    # ==================== 3.5 调用各策略的盘前准备函数 ====================
    # 调用测试策略1的盘前准备函数（如果已注册）
    if g.test_mode and g.strategy_registration.get('test_1', False) and hasattr(g, 'test_strategy_1'):
        try:
            g.test_strategy_1.before_trading_start(context)
        except Exception as e:
            log.error(f"调用测试策略1盘前准备失败: {str(e)}")
    
    # 调用测试策略2的盘前准备函数（如果已注册）
    if g.test_mode and g.strategy_registration.get('test_2', False) and hasattr(g, 'test_strategy_2'):
        try:
            g.test_strategy_2.before_trading_start(context)
        except Exception as e:
            log.error(f"调用测试策略2盘前准备失败: {str(e)}")


def _clear_daily_variables(context):
    """
    清空当日变量
    
    重置每日需要清空的变量，包括：
    - 当日交易记录
    - 当日买卖标记
    - 当日统计信息
    """
    # 重置当日交易记录
    if not hasattr(g, 'today_trades'):
        g.today_trades = []
    g.today_trades = []
    
    # 重置当日买卖股票集合
    g.today_bought_stocks = set()
    g.today_sold_stocks = set()
    
    # 重置当日执行标记
    g.buy_executed = False
    g.sell_executed = False
    
    # 重置当日市场统计
    g.today_market_stats = {
        'up_count': 0,
        'down_count': 0,
        'limit_up_count': 0,
        'limit_down_count': 0,
        'total_value': 0,
        'total_cash': 0
    }
    
    log.info("当日变量已清空")


def _get_market_data(context):
    """
    获取市场数据
    
    包括：
    - 大盘指数数据
    - 涨跌停统计
    - 市场整体表现
    
    注意：在开盘前（09:25），只能获取昨日收盘价，不能获取当日收盘价
    """
    try:
        # 获取基准指数（沪深300）昨日收盘价（开盘前只能获取昨日数据）
        # 使用 context.previous_date 获取昨日日期
        yesterday = context.previous_date
        benchmark_data = get_price(BENCHMARK, end_date=yesterday, count=1, frequency='daily', fields=['close'], panel=False)
        
        if benchmark_data is not None and not benchmark_data.empty:
            benchmark_price = float(benchmark_data['close'].iloc[-1])
            g.today_market_stats['benchmark'] = benchmark_price
            log.info(f"基准指数({BENCHMARK})昨日收盘价: {benchmark_price:.2f}")
        else:
            log.warning(f"未能获取基准指数({BENCHMARK})昨日收盘价数据")
        
        # 获取账户总市值和现金
        g.today_market_stats['total_value'] = context.portfolio.total_value
        g.today_market_stats['total_cash'] = context.portfolio.cash
        log.info(f"总市值: {g.today_market_stats['total_value']:.2f}, 现金: {g.today_market_stats['total_cash']:.2f}")
        
        # 获取持仓股票数量
        position_count = len(context.portfolio.positions)
        g.today_market_stats['position_count'] = position_count
        log.info(f"持仓数量: {position_count}")
        
        # 可以添加更多市场数据获取逻辑
        # - 涨跌停统计
        # - 市场涨跌家数
        # - 成交量等
        
    except Exception as e:
        log.error(f"获取市场数据失败: {str(e)}")


def _check_empty_position_condition(context):
    """
    检查空仓条件
    
    根据市场环境和策略规则判断是否需要空仓
    """
    try:
        # 检查市场状态是否要求空仓
        if g.market_state.get('is_empty', False):
            log.info("市场状态标记为空仓，跳过交易")
            return
        
        # 主策略空仓条件判断
        # 辅助策略空仓月判断
        
        # 检查账户资金是否过少
        if context.portfolio.total_value < 10000:
            log.warning(f"账户总市值过小（{context.portfolio.total_value:.2f}），建议空仓")
            g.market_state['is_empty'] = True
        
    except Exception as e:
        log.error(f"检查空仓条件失败: {str(e)}")


def _check_cooldown_status(context):
    """
    检查冷静期状态
    
    检查各策略是否处于冷静期，并根据冷静期规则执行相应操作
    
    功能说明：
    1. 检查SwingStrategy（test_strategy_1）的冷静期状态
    2. 打印冷静期状态信息（是否在冷静期、冷静期天数等）
    3. 如果不在冷静期，调用组合跌幅监控逻辑
    
    实现参考：
    min_cooldown_swing_strategy.py 中的冷静期管理逻辑
    SwingStrategy 类中的 in_cooldown、days_since_sell 等状态变量
    """
    try:
        # 检查SwingStrategy（test_strategy_1）是否注册
        if g.test_mode and g.strategy_registration.get('test_1', False) and hasattr(g, 'test_strategy_1'):
            strategy = g.test_strategy_1
            
            # 获取冷静期状态
            in_cooldown = getattr(strategy, 'in_cooldown', False)
            days_since_sell = getattr(strategy, 'days_since_sell', 0)
            cooldown_days = getattr(strategy, 'cooldown_days', 5)
            last_sell_date = getattr(strategy, 'last_sell_date', None)
            
            # 打印冷静期状态
            if in_cooldown:
                log.info(f"[冷静期状态] {strategy.strategy_id} 当前处于冷静期（已过天数: {days_since_sell}/{cooldown_days}）")
            else:
                pass
            
            # 如果不在冷静期，检查组合跌幅（调用组合跌幅监控逻辑）
            # 注意：组合跌幅监控也在swing_strategy_portfolio_monitor定时任务中执行（09:30）
            # 这里为了保持冷静期状态的连续性，也在盘前检查一次
            if not in_cooldown:
                # 计算组合收益
                daily_return = strategy.calculate_portfolio_return(context)
                
                # 检查是否触发冷静期
                is_triggered = strategy.check_portfolio_decline(context)
                
                if is_triggered:
                    log.info(f"[冷静期状态] {strategy.strategy_id} 组合跌幅触发冷静期")
                else:
                    log.debug(f"[冷静期状态] {strategy.strategy_id} 组合正常，未触发冷静期")
            
        else:
            log.debug("[冷静期状态] SwingStrategy未注册，跳过冷静期检查")
            
    except Exception as e:
        log.error(f"检查冷静期状态失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())


def swing_strategy_buy(context):
    """
    SwingStrategy买入任务（09:31定时任务调用）
    
    功能说明：
    - 调用test_strategy_1（SwingStrategy实例）的buy_stocks方法
    - 执行买入逻辑
    
    参数:
        context: 聚宽上下文对象
    """
    try:
        if hasattr(g, 'test_strategy_1') and g.test_strategy_1:
            g.test_strategy_1.buy_stocks(context)
        else:
            log.warning("[定时任务] swing_strategy_buy: test_strategy_1未注册")
    except Exception as e:
        log.error(f"[定时任务] swing_strategy_buy执行失败: {str(e)}")


def swing_strategy_sell(context):
    """
    SwingStrategy卖出任务（14:49定时任务调用）
    
    功能说明：
    - 调用test_strategy_1（SwingStrategy实例）的sell_stocks方法
    - 执行卖出逻辑
    
    参数:
        context: 聚宽上下文对象
    """
    try:
        if hasattr(g, 'test_strategy_1') and g.test_strategy_1:
            g.test_strategy_1.sell_stocks(context)
        else:
            log.warning("[定时任务] swing_strategy_sell: test_strategy_1未注册")
    except Exception as e:
        log.error(f"[定时任务] swing_strategy_sell执行失败: {str(e)}")


def swing_strategy_interval_control(context):
    """
    SwingStrategy分钟级风控任务（每分钟执行）
    
    功能说明：
    - 调用test_strategy_1（SwingStrategy实例）的interval_sell_buy方法
    - 执行分钟级风控逻辑
    - 止盈：涨幅达到8%则清仓
    - 回补：跌幅达到-3%且当日未买过且不在冷却期可买回
    
    参数:
        context: 聚宽上下文对象
    """
    try:
        if hasattr(g, 'test_strategy_1') and g.test_strategy_1:
            # 仅在有持仓时才执行（减少不必要的日志输出）
            if context.portfolio.positions and len(context.portfolio.positions) > 0:
                g.test_strategy_1.interval_sell_buy(context)
        else:
            log.warning("[定时任务] swing_strategy_interval_control: test_strategy_1未注册")
    except Exception as e:
        log.error(f"[定时任务] swing_strategy_interval_control执行失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())


def swing_strategy_portfolio_monitor(context):
    """
    SwingStrategy组合跌幅监控任务（09:30定时任务调用）
    
    功能说明：
    - 调用test_strategy_1（SwingStrategy实例）的calculate_portfolio_return方法
    - 调用test_strategy_1（SwingStrategy实例）的check_portfolio_decline方法
    - 记录组合收益和冷静期状态
    
    参数:
        context: 聚宽上下文对象
    """
    try:
        if hasattr(g, 'test_strategy_1') and g.test_strategy_1:
            # 计算组合收益
            daily_return = g.test_strategy_1.calculate_portfolio_return(context)
            
            # 检查是否触发冷静期
            is_triggered = g.test_strategy_1.check_portfolio_decline(context)
            
            if is_triggered:
                log.info("[定时任务] swing_strategy_portfolio_monitor: 触发冷静期")
        else:
            log.warning("[定时任务] swing_strategy_portfolio_monitor: test_strategy_1未注册")
    except Exception as e:
        log.error(f"[定时任务] swing_strategy_portfolio_monitor执行失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())


# _test_filter_functions函数已完全删除（测试代码，约754行）


def after_trading_end(context):
    """
    每日盘后处理函数
    
    功能说明：
    1. 撤销所有未完成订单
    2. 记录当日交易日志
    3. 更新策略绩效统计
    4. 检查资金池调整（每月）
    5. 输出每日总结报告
    """
    # ==================== 4.1 撤销所有未完成订单 ====================
    _cancel_all_orders(context)
    
    # ==================== 4.2 记录当日交易日志 ====================
    log_daily_trades(context)
    
    # ==================== 4.3 更新策略绩效统计 ====================
    _update_strategy_performance(context)
    
    # ==================== 4.4 检查资金池调整（每月） ====================
    _check_capital_pool_adjustment(context)
    
    # ==================== 4.5 输出每日总结报告 ====================
    _output_daily_summary(context)
    
    # ==================== 4.6 调用各策略的盘后处理函数 ====================
    # 调用测试策略1的盘后处理函数（如果已注册）
    if g.test_mode and g.strategy_registration.get('test_1', False) and hasattr(g, 'test_strategy_1'):
        try:
            g.test_strategy_1.after_trading_end(context)
            log.info("策略盘后处理: 已调用测试策略1")
        except Exception as e:
            log.error(f"调用测试策略1盘后处理失败: {str(e)}")
    
    # 调用测试策略2的盘后处理函数（如果已注册）
    if g.test_mode and g.strategy_registration.get('test_2', False) and hasattr(g, 'test_strategy_2'):
        try:
            g.test_strategy_2.after_trading_end(context)
            log.info("策略盘后处理: 已调用测试策略2")
        except Exception as e:
            log.error(f"调用测试策略2盘后处理失败: {str(e)}")
    
    log.info(f"=" * 60)
    log.info(f"盘后处理完成")
    log.info(f"=" * 60)


def _cancel_all_orders(context):
    """
    撤销所有未完成订单
    """
    try:
        # 获取所有未完成的订单
        orders = get_open_orders()
        if orders:
            log.info(f"发现 {len(orders)} 个未完成订单，正在撤销...")
            for order in orders:
                try:
                    cancel_order(order.order_id)
                    log.info(f"已撤销订单: {order.security} - 数量: {order.amount}")
                except Exception as e:
                    log.error(f"撤销订单失败: {order.security} - {str(e)}")
        else:
            log.info("没有未完成的订单")
    except Exception as e:
        log.error(f"撤销订单过程出错: {str(e)}")


def _update_strategy_performance(context):
    """
    更新策略绩效统计
    
    统计各策略的当日表现，包括：
    - 当日收益率
    - 持仓市值
    - 交易次数
    - 盈亏情况
    
    日收益计算说明：
    - 计算公式：(当日收盘总市值 - 昨日收盘总市值) / 昨日收盘总市值
    - 本函数在 after_trading_end (15:30) 执行，使用15:30时的总市值
    - 与聚宽平台的差异可能在于：平台可能使用15:00收盘时的总市值
    """
    try:
        # 获取账户总市值
        total_value = context.portfolio.total_value
        cash = context.portfolio.cash
        position_value = total_value - cash
        
        # 计算当日收益率（需要与昨日市值对比）
        yesterday_value = total_value  # 默认值
        daily_return = 0.0
        daily_return_abs = 0.0
        
        if len(g.trade_stats['daily_returns']) > 0:
            yesterday_value = g.trade_stats['daily_returns'][-1].get('total_value', total_value)
            daily_return_abs = total_value - yesterday_value
            daily_return = daily_return_abs / yesterday_value if yesterday_value > 0 else 0.0
        else:
            # 第一天没有昨日数据，当日收益为0
            log.info("【日收益计算】第一日无昨日数据，当日收益设为0")
        
        # 记录当日收益（整体）
        g.trade_stats['daily_returns'].append({
            'date': transform_date(context.current_dt, 'str_yyyy_mm_dd'),
            'total_value': total_value,
            'cash': cash,
            'position_value': position_value,
            'daily_return': daily_return,
            'daily_return_abs': daily_return_abs
        })
        
        # ========== 新增：记录各策略的绩效数据 ==========
        # 用于资金池分配计算
        if hasattr(g, 'strategy_manager') and hasattr(g.strategy_manager, 'strategies'):
            for strategy_id in g.strategy_manager.strategies.keys():
                # 初始化策略绩效数据
                if strategy_id not in g.trade_stats['strategy_performance']:
                    g.trade_stats['strategy_performance'][strategy_id] = {
                        'daily_returns': [],
                        'total_trades': 0,
                        'total_profit': 0.0
                    }
                
                # ========== 计算策略真实收益率 ==========
                # 获取该策略的持仓股票（通过g.strategy_tags）
                strategy_stocks = []
                if hasattr(g, 'strategy_tags'):
                    strategy_stocks = [stock for stock, sid in g.strategy_tags.items() if sid == strategy_id]
                
                strategy_daily_return = daily_return  # 默认使用整体收益率
                
                if strategy_stocks and hasattr(g, 'last_strategy_values'):
                    # 有持仓且有历史数据，计算真实收益率
                    strategy_value_today = 0.0
                    strategy_value_yesterday = 0.0
                    
                    for stock in strategy_stocks:
                        position = context.portfolio.positions.get(stock)
                        if position and position.total_amount > 0:
                            # 当日市值
                            stock_value_today = position.total_amount * position.price
                            strategy_value_today += stock_value_today
                            
                            # 昨日市值（从历史记录中获取）
                            stock_value_yesterday = g.last_strategy_values.get(stock, stock_value_today)
                            strategy_value_yesterday += stock_value_yesterday
                    
                    # 计算策略收益率
                    if strategy_value_yesterday > 0:
                        strategy_daily_return = (strategy_value_today - strategy_value_yesterday) / strategy_value_yesterday
                    
                    log.info(f"【策略绩效】{strategy_id}: 昨日市值={strategy_value_yesterday:.2f}, "
                           f"今日市值={strategy_value_today:.2f}, 收益率={strategy_daily_return:.4%}")
                elif strategy_stocks:
                    # 有持仓但没有历史数据，记录当前市值
                    strategy_value_today = 0.0
                    for stock in strategy_stocks:
                        position = context.portfolio.positions.get(stock)
                        if position and position.total_amount > 0:
                            stock_value_today = position.total_amount * position.price
                            strategy_value_today += stock_value_today
                    
                    log.info(f"【策略绩效】{strategy_id}: 今日市值={strategy_value_today:.2f}（无历史数据）")
                else:
                    # 无持仓，收益率为0
                    strategy_daily_return = 0.0
                    log.info(f"【策略绩效】{strategy_id}: 无持仓，收益率=0%")
                
                # 记录策略日收益率
                g.trade_stats['strategy_performance'][strategy_id]['daily_returns'].append(strategy_daily_return)
                
                # 统计策略交易次数
                if hasattr(g, 'today_trades'):
                    # 过滤掉None值（交易失败的记录）
                    valid_trades = [t for t in g.today_trades if t is not None]
                    strategy_trades = [t for t in valid_trades if t.get('strategy_id') == strategy_id]
                    g.trade_stats['strategy_performance'][strategy_id]['total_trades'] += len(strategy_trades)
                    
                    # 计算策略盈亏
                    for trade in strategy_trades:
                        if trade.get('action') == '卖出':
                            profit = trade.get('profit', 0)
                            g.trade_stats['strategy_performance'][strategy_id]['total_profit'] += profit
        
        # ========== 记录昨日持仓市值（用于下次计算策略收益率） ==========
        if hasattr(g, 'strategy_tags'):
            g.last_strategy_values = {}
            for stock, strategy_id in g.strategy_tags.items():
                position = context.portfolio.positions.get(stock)
                if position and position.total_amount > 0:
                    g.last_strategy_values[stock] = position.total_amount * position.price
        
        # 计算总收益（相对于初始资金）
        initial_capital = getattr(g, 'initial_capital', total_value)
        total_profit = total_value - initial_capital
        total_profit_pct = (total_profit / initial_capital * 100) if initial_capital > 0 else 0
        
        # 输出详细的日收益计算信息
        log.info(f"账户市值: {total_value:.2f}, 现金: {cash:.2f}, 持仓: {position_value:.2f}, "
               f"当日收益: {daily_return:.2%} ({daily_return_abs:+.2f}), 总收益: {total_profit_pct:+.2f}%")
        
        # 输出日收益计算详情（用于调试）
        if len(g.trade_stats['daily_returns']) > 1:
            log.info(f"【日收益计算详情】")
            log.info(f"  昨日总市值: {yesterday_value:.2f}")
            log.info(f"  当日总市值: {total_value:.2f}")
            log.info(f"  变动金额: {daily_return_abs:+.2f}")
            log.info(f"  日收益率: {daily_return:.4%}")
            log.info(f"  计算时间: {transform_date(context.current_dt, 'str_yyyy_mm_dd_hh_mm_ss')}")
            
            # 检查是否有交易，并计算交易成本
            if hasattr(g, 'today_trades') and len(g.today_trades) > 0:
                # 过滤掉None值（交易失败的记录）
                valid_trades = [t for t in g.today_trades if t is not None]
                buy_count = len([t for t in valid_trades if t.get('action') == '买入'])
                sell_count = len([t for t in valid_trades if t.get('action') == '卖出'])
                log.info(f"  当日交易: 买入{buy_count}次, 卖出{sell_count}次")
            else:
                log.info(f"  当日交易: 无")
        
    except Exception as e:
        log.error(f"更新策略绩效统计失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())


def _check_capital_pool_adjustment(context):
    """
    检查资金池调整（按配置的N个月周期）
    
    任务10：支持市场停牌检测，遇到节假日顺延调整日期
    任务11：支持按每N个月调整（N可配置），最低间隔20个交易日
    """
    try:
        # ========== 任务10：市场停牌检测 ==========
        log.info("[资金池] 开始市场停牌检测")
        
        # 获取当前日期
        current_date = context.current_dt
        current_month = current_date.month
        
        # 获取所有交易日
        all_trade_days = get_trade_days(start_date=current_date.date(), end_date=current_date.date() + timedelta(days=30))
        
        # 检查今天是否为交易日
        today = current_date.date()
        is_trading_day = today in all_trade_days
        
        if not is_trading_day:
            log.warning(f"[资金池] 今天（{today}）不是交易日，跳过资金池调整")
            return False
        
        log.info(f"[资金池] 今天（{today}）是交易日，继续检查调整条件")
        
        # 初始化上一次调整的月份记录
        if not hasattr(g, 'last_adjustment_month'):
            g.last_adjustment_month = -1  # 初始化为-1，确保第一个月会进行调整
        
        # ========== 任务11：调整周期配置 ==========
        # 获取StrategyManager的调整周期配置
        adjustment_interval_months = 1  # 默认为1个月
        min_trading_days = 20  # 默认为20个交易日
        
        if hasattr(g, 'strategy_manager') and hasattr(g.strategy_manager, 'allocation_config'):
            adjustment_interval_months = g.strategy_manager.allocation_config.get('adjustment_interval_months', 1)
            min_trading_days = g.strategy_manager.allocation_config.get('min_trading_days', 20)
        
        log.info(f"[资金池] 调整周期配置: 每{adjustment_interval_months}个月调整一次，最低间隔{min_trading_days}个交易日")
        
        # 获取当前年份
        current_year = current_date.year
        
        # 检查是否为调整月份（当前月份 - 上次调整月份 >= 调整间隔）
        months_since_last_adjustment = current_year * 12 + current_month - (
            (g.last_adjustment_year * 12 + g.last_adjustment_month) 
            if hasattr(g, 'last_adjustment_year') and hasattr(g, 'last_adjustment_month') 
            else -12
        )
        
        is_adjustment_month = months_since_last_adjustment >= adjustment_interval_months
        
        if is_adjustment_month:
            log.info(f"今日为调整月（距离上次调整已过{months_since_last_adjustment}个月），检查资金池调整...")
            
            # 检查交易日间隔
            trading_days_since_last_adjustment = getattr(g, 'trading_days_since_last_adjustment', 0)
            trading_days_since_last_adjustment += 1  # 每个交易日增加1
            g.trading_days_since_last_adjustment = trading_days_since_last_adjustment
            
            log.info(f"[资金池] 自上次调整以来的交易日数: {trading_days_since_last_adjustment}/{min_trading_days}")
            
            # 检查是否满足最低交易日数要求
            if trading_days_since_last_adjustment < min_trading_days:
                log.info(f"[资金池] 交易日数未达到最低要求（{min_trading_days}天），暂不调整资金池")
                return False
            
            # 调用StrategyManager的资金池分配方法
            if hasattr(g, 'strategy_manager'):
                success = g.strategy_manager.allocate_capital_pools(context)
                if success:
                    log.info("✓ 资金池分配成功")
                    # 更新上一次调整的月份和年份
                    g.last_adjustment_month = current_month
                    g.last_adjustment_year = current_year
                    # 重置交易日计数
                    g.trading_days_since_last_adjustment = 0
                else:
                    log.warning("✗ 资金池分配失败")
            else:
                log.warning("未找到strategy_manager，跳过资金池分配")
        else:
            # 非调整月，记录当前资金池状态
            if hasattr(g, 'strategy_manager') and hasattr(g.strategy_manager, 'capital_pools'):
                current_day = current_date.day
                months_remaining = adjustment_interval_months - months_since_last_adjustment
                log.info(f"当前资金池状态（非调整日，本月{current_day}号，距下次调整还有{months_remaining}个月）:")
                for strategy_id, pool in g.strategy_manager.capital_pools.items():
                    log.info(f"  {strategy_id}: {pool['ratio']:.2%} ({pool['amount']:.2f}元)")
        
    except Exception as e:
        log.error(f"检查资金池调整失败: {str(e)}")


def _output_daily_summary(context):
    """
    输出每日总结报告
    
    包括：
    - 账户总览
    - 持仓情况
    - 交易汇总
    - 市场统计
    """
    try:
        log.info("\n==== 每日总结报告 ====")
        
        # 账户总览
        total_value = context.portfolio.total_value
        cash = context.portfolio.cash
        position_value = total_value - cash
        position_count = len(context.portfolio.positions)
        
        # 计算总收益（相对于初始资金）
        initial_capital = getattr(g, 'initial_capital', total_value)
        total_profit = total_value - initial_capital
        total_profit_pct = (total_profit / initial_capital * 100) if initial_capital > 0 else 0
        
        log.info(f"【账户总览】")
        log.info(f"  初始资金: {initial_capital:.2f}")
        log.info(f"  总市值: {total_value:.2f}")
        log.info(f"  现金: {cash:.2f} ({cash/total_value*100:.1f}%)")
        log.info(f"  持仓: {position_value:.2f} ({position_value/total_value*100:.1f}%)")
        log.info(f"  持仓数量: {position_count}")
        log.info(f"  总收益: {total_profit:.2f} ({total_profit_pct:+.2f}%)")
        
        # 持仓明细
        if position_count > 0:
            log.info(f"\n【持仓明细】")
            current_data = get_current_data()
            
            # 计算总持仓市值（从账户总览获取，这是准确的实时市值）
            total_position_value = position_value
            
            # 计算所有股票的成本市值总和（用于按比例分配）
            total_cost_value = sum(
                position.avg_cost * position.total_amount
                for position in context.portfolio.positions.values()
            )
            
            for code, position in context.portfolio.positions.items():
                try:
                    # 获取股票名称（使用历史时间点的信息，避免未来函数）
                    # 说明：不显示股票名称，因为get_security_info会返回当前时间点的信息，
                    #      如果股票后来变成了ST，会导致显示不准确（未来函数问题）
                    #      只显示股票代码，避免误导
                    stock_name = ""  # 不显示股票名称
                    
                    # 获取持仓信息
                    amount = position.total_amount
                    avg_cost = position.avg_cost
                    cost_value = avg_cost * amount
                    
                    # 按成本市值比例分配总持仓市值（确保总和等于账户总览的持仓市值）
                    if total_cost_value > 0 and cost_value > 0:
                        ratio = cost_value / total_cost_value
                        market_value = total_position_value * ratio
                    else:
                        market_value = cost_value  # 兜底：使用成本市值
                    
                    # 计算盈亏（市值 - 成本）
                    profit = market_value - cost_value
                    
                    # 只显示股票代码，不显示股票名称（避免未来函数问题）
                    log.info(f"  {code}: "
                           f"数量: {amount:.0f}, "
                           f"市值: {market_value:.2f}, "
                           f"成本: {avg_cost:.2f}, "
                           f"盈亏: {profit:.2f}")
                except Exception as e:
                    log.warning(f"  {code}: 获取持仓详情失败 - {str(e)}")
        
        # 市场统计
        if hasattr(g, 'today_market_stats'):
            log.info(f"\n【市场统计】")
            log.info(f"  基准指数({BENCHMARK}): {g.today_market_stats.get('benchmark', 'N/A')}")
            log.info(f"  持仓数量: {g.today_market_stats.get('position_count', 0)}")
        
        # 交易汇总
        if hasattr(g, 'today_trades') and len(g.today_trades) > 0:
            buy_count = len([t for t in g.today_trades if t['action'] == '买入'])
            sell_count = len([t for t in g.today_trades if t['action'] == '卖出'])
            log.info(f"\n【交易汇总】")
            log.info(f"  买入次数: {buy_count}")
            log.info(f"  卖出次数: {sell_count}")
            log.info(f"  总交易次数: {len(g.today_trades)}")
        
        log.info("==== 每日总结结束 ====\n")
        
    except Exception as e:
        log.error(f"输出每日总结报告失败: {str(e)}")


# ============================================================================
# 4. 基础工具函数
# ============================================================================

# 4.1 日期时间处理函数
# ============================================================================

def transform_date(date_input: Any, output_format: str = 'str_yyyy_mm_dd') -> Optional[Union[str, dt.datetime, dt.date, int]]:
    """
    日期格式转换函数
    
    参数:
        date_input: 输入日期（支持datetime/date/str/timestamp/numpy/pandas）
        output_format: 输出格式（'str_yyyy_mm_dd'/'str_yyyymmdd'/'datetime'/'date'/'timestamp'）
    
    返回:
        转换后的日期，失败返回None
    """
    try:
        if date_input is None:
            return None
        
        # 步骤1：统一转换为 datetime 对象
        dt_obj = None
        
        # 情况1：输入已经是 datetime 对象
        if isinstance(date_input, dt.datetime):
            dt_obj = date_input
        
        # 情况2：输入是 date 对象
        elif isinstance(date_input, dt.date):
            dt_obj = dt.datetime.combine(date_input, dt.time(0, 0, 0))
        
        # 情况3：输入是 pandas.Timestamp
        elif isinstance(date_input, pd.Timestamp):
            dt_obj = date_input.to_pydatetime()
        
        # 情况4：输入是 numpy.datetime64
        elif isinstance(date_input, np.datetime64):
            dt_obj = pd.Timestamp(date_input).to_pydatetime()
        
        # 情况5：输入是时间戳
        elif isinstance(date_input, (int, float)):
            dt_obj = dt.datetime.fromtimestamp(date_input)
        
        # 情况6：输入是字符串
        elif isinstance(date_input, str):
            date_str = date_input.strip()
            
            # 尝试不同的日期格式
            date_formats = [
                '%Y-%m-%d',      # '2026-02-02'
                '%Y/%m/%d',      # '2026/02/02'
                '%Y%m%d',        # '20260202'
                '%Y-%m-%d %H:%M:%S',  # '2026-02-02 10:30:00'
                '%Y/%m/%d %H:%M:%S',  # '2026/02/02 10:30:00'
                '%Y%m%d%H%M%S',  # '20260202103000'
            ]
            
            for fmt in date_formats:
                try:
                    dt_obj = dt.datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            
            # 如果所有格式都不匹配，尝试其他方式
            if dt_obj is None:
                # 尝试直接转换（处理 '20260202' 格式）
                if len(date_str) == 8 and date_str.isdigit():
                    year = date_str[:4]
                    month = date_str[4:6]
                    day = date_str[6:8]
                    dt_obj = dt.datetime(int(year), int(month), int(day))
        
        # 情况7：无法识别的类型
        if dt_obj is None:
            log.warning(f"无法识别的日期格式: {date_input} (类型: {type(date_input)})")
            return None
    except Exception as e:
        log.error(f"日期转换失败: 输入={date_input}, 输出格式={output_format}, 错误={str(e)}")
        import traceback
        log.error(traceback.format_exc())
        return None
        
        # 4.2 交易时段判断函数
        # ============================================================================
        
def get_trading_time_status(context: Any, time_input: Optional[Union[dt.time, str]] = None) -> Optional[str]:
    """
    交易时段判断函数
    
    参数:
        context: 策略上下文对象
        time_input: 输入时间（None/context.current_dt/datetime.time/str）
    
    返回:
        str: 交易时段标识（'pre_market'/'morning'/'lunch_break'/'afternoon'/'after_market'/'non_trading'）
    """
    try:
        # 定义交易时段（转换为分钟数，便于比较）
        # A股交易时段：
        # - 盘前集合竞价：09:25 - 09:30 (565-570分钟)
        # - 上午交易：09:30 - 11:30 (570-690分钟)
        # - 午休：11:30 - 13:00 (690-780分钟)
        # - 下午交易：13:00 - 15:00 (780-900分钟)
        # - 盘后：15:00 以后 (900分钟以上)
        
        # ==================== 步骤1：获取当前时间（分钟数）====================
        hour = 0
        minute = 0
        
        if time_input is None:
            # 从 context.current_dt 获取
            try:
                # 聚宽的 context.current_dt 可能是 Timestamp 或其他类型
                # 使用 hasattr 检查属性，然后用 getattr 获取
                if hasattr(context.current_dt, 'hour'):
                    hour = context.current_dt.hour
                    minute = context.current_dt.minute
                else:
                    # 尝试转换为 pandas.Timestamp
                    ts = pd.Timestamp(context.current_dt)
                    hour = ts.hour
                    minute = ts.minute
            except Exception as e:
                log.error(f"从 context.current_dt 获取时间失败: {str(e)}")
                return None
        
        elif isinstance(time_input, dt.time):
            hour = time_input.hour
            minute = time_input.minute
        
        elif isinstance(time_input, str):
            # 解析字符串时间格式
            try:
                if ':' in time_input:
                    parts = time_input.split(':')
                    hour = int(parts[0])
                    minute = int(parts[1])
            except Exception as e:
                log.error(f"解析时间字符串失败: {time_input}, 错误={str(e)}")
                return None
        
        else:
            log.warning(f"无法识别的时间输入: {time_input} (类型: {type(time_input)})")
            return None
        
        # ==================== 步骤2：判断交易时段 ====================
        current_time_minutes = hour * 60 + minute
        
        # 判断时段
        if 565 <= current_time_minutes < 570:
            # 盘前集合竞价：09:25 - 09:30
            return 'pre_market'
        
        elif 570 <= current_time_minutes < 690:
            # 上午交易：09:30 - 11:30
            return 'morning'
        
        elif 690 <= current_time_minutes < 780:
            # 午休：11:30 - 13:00
            return 'lunch_break'
        
        elif 780 <= current_time_minutes < 900:
            # 下午交易：13:00 - 15:00
            return 'afternoon'
        
        elif current_time_minutes >= 900:
            # 盘后：15:00 以后
            return 'after_market'
        
        else:
            # 非交易时段：00:00 - 09:25
            return 'non_trading'
    
    except Exception as e:
        log.error(f"交易时段判断失败: 输入={time_input}, 错误={str(e)}")
        import traceback
        log.error(traceback.format_exc())
        return None
        
        # 4.3 交易日相关函数
        # ============================================================================
        
def _is_first_trading_day_of_month(context):
    """
    判断是否是每月第一个交易日
    
    功能说明：
    - 获取当前日期所在的月份
    - 获取该月的第一个交易日
    - 判断当前日期是否是该月的第一个交易日
    
    参数:
        context: 聚宽上下文对象
    
    返回:
        bool: True表示是每月第一个交易日，False表示不是
    
    实现参考：
        min_cooldown_swing_strategy.py 中的 _is_first_trading_day_in_month 函数
    """
    try:
        # 获取当前日期
        cur = context.current_dt.date()
        
        # 获取该月的1号
        month_start = cur.replace(day=1)
        
        # 获取从该月1号到当前日期的所有交易日
        days = get_trade_days(start_date=month_start, end_date=cur)
        
        # 如果有交易日，且第一个交易日就是今天，则是每月第一个交易日
        if days and len(days) >= 1 and days[0] == cur:
            return True
        
        return False
    
    except Exception as e:
        log.error(f"判断每月第一个交易日失败: {str(e)}")
        return False


# ============================================================================
# 4.4 股票过滤函数
# ============================================================================

def filter_st_paused_stock(codes: List[str]) -> List[str]:
    """
    过滤停牌股票、ST股票、退市股票
    
    功能说明：
    1. 过滤停牌股票（paused）
    2. 过滤ST股票（is_st）
    3. 过滤退市股票（名称中包含"退"或"退市"）
    4. 过滤名称中包含ST的所有大小写变体（'ST'、'st'、'St'、'sT'）
    5. 过滤名称中包含*ST的所有大小写变体（'*ST'、'*st'、'*St'）
    
    实盘移植说明：
    - QMT/PTrade平台：需要根据各平台的ST判断规则进行调整
    - 数据获取方式：get_current_data() 在不同平台可能有不同的API
    - 特殊处理：需要考虑各平台的特殊股票状态（如PT、退市整理期等）
    
    参数:
        codes: 股票代码列表（如 ['000001.XSHE', '600000.XSHG']）
    
    返回:
        过滤后的股票代码列表
    
    实现参考：
        min_cooldown_swing_strategy.py 中的 _filter_st_pause_delist 函数
    """
    if not codes:
        return []
    
    current_data = get_current_data()
    out = []
    
    for s in codes:
        try:
            info = current_data[s]
            name = info.name
            
            # 检查1：is_st标记
            if info.is_st:
                continue
            
            # 检查2：停牌状态
            if info.paused:
                continue
            
            # 检查3：名称检查（处理编码问题，检查所有大小写变体）
            if name:
                # 检查是否包含'ST'（所有大小写变体）
                if 'ST' in name or 'st' in name or 'St' in name or 'sT' in name:
                    continue
                # 检查是否包含'*ST'（所有大小写变体）
                if '*ST' in name or '*st' in name or '*St' in name:
                    continue
                # 检查是否包含'退'（退市股票）
                if '退' in name or '退市' in name:
                    continue
            
            out.append(s)
        except:
            continue
    
    return out


def filter_new_stock(codes: List[str], context: Optional[Any] = None, min_days: int = 60) -> List[str]:
    """
    过滤新股（上市不足指定天数的股票）
    
    功能说明：
    1. 根据上市天数过滤新股
    2. 支持自定义上市天数阈值（默认60天）
    3. 避免新股风险
    
    参数:
        codes: 股票代码列表（如 ['000001.XSHE', '600000.XSHG']）
        context: 策略上下文对象，用于获取当前日期（可选）
        min_days: 最小上市天数阈值，默认60天
    
    返回:
        过滤后的股票代码列表
    
    实现参考：
        Enhanced_5in1_LimitUp_Trading_Strategy.py 中的 filter_new_stock 函数
    """
    if not codes:
        return []
    
    # 获取参考日期（使用 context.previous_date 避免未来数据）
    if context is not None:
        ref_date = context.previous_date
    else:
        # 如果没有 context，使用当前日期（仅用于测试）
        ref_date = dt.date.today()
    
    # 将 ref_date 转换为 datetime.date 对象（如果是 datetime.datetime）
    if isinstance(ref_date, dt.datetime):
        ref_date = ref_date.date()
    
    filtered_stocks = []
    filtered_info = []  # 记录被过滤的股票信息
    
    for stock in codes:
        try:
            # 获取股票上市日期
            security_info = get_security_info(stock)
            if security_info is None:
                continue
            
            start_date = security_info.start_date
            
            # 计算上市天数
            days_listed = (ref_date - start_date).days
            
            # 检查是否满足最小上市天数
            if days_listed >= min_days:
                filtered_stocks.append(stock)
            else:
                # 记录被过滤的股票
                filtered_info.append({
                    'code': stock,
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'days_listed': days_listed
                })
        except Exception as e:
            # 如果获取失败，保守处理：保留该股票
            log.warning(f"获取股票 {stock} 的上市日期失败，保留该股票: {str(e)}")
            filtered_stocks.append(stock)
    
    # 输出过滤统计
    if filtered_info:
        log.info(f"【过滤新股】过滤掉 {len(filtered_info)} 只上市不足 {min_days} 天的股票:")
        for info in filtered_info[:5]:  # 只显示前5个
            log.info(f"  - {info['code']}: 上市{info['days_listed']}天 ({info['start_date']})")
        if len(filtered_info) > 5:
            log.info(f"  ... 还有 {len(filtered_info) - 5} 只")
    
    return filtered_stocks


# ============================================================================
# 4.5 ETF池获取和筛选函数
# ============================================================================

# ============================================================================
# 总控决策模块（StrategyManager类）
# ============================================================================

class StrategyManager:
    """
    总控决策管理器
    
    功能说明：
    1. 策略注册和管理
    2. 资金池动态分配
    3. 策略优先级管理
    4. 买卖冲突避免
    5. 季度资金调整（每季度第一个交易日）
    
    实盘移植说明：
    - QMT/PTrade平台：需要根据各平台的账户管理API进行调整
    - 资金池管理：需要考虑各平台的资金限制和风控规则
    - 策略协调：需要确保多策略之间的资源隔离和优先级管理
    - 性能优化：实盘环境下需要考虑性能优化和资源限制
    
    设计原则：
    - 单例模式：全局只有一个StrategyManager实例
    - 线程安全：所有方法支持并发调用
    - 可扩展性：方便添加新策略
    """
    
    def __init__(self):
        """
        StrategyManager类初始化函数
        
        初始化内容：
        - 策略实例字典
        - 资金池字典
        - 优先级顺序列表
        - 策略标签系统
        - 统计信息
        - 全仓模式配置
        """
        # ========== 策略实例字典 ==========
        self.strategies = {}  # {strategy_id: strategy_instance}
        
        # ========== 资金池字典 ==========
        self.capital_pools = {}  # {strategy_id: {'amount': float, 'ratio': float}}
        
        # ========== 优先级顺序列表 ==========
        self.priority_order = []  # [strategy_id1, strategy_id2, ...]
        
        # ========== 资金分配配置 ==========
        self.allocation_config = {
            'last_allocation_date': None,  # 上次资金分配日期
            'monthly_adjustment_day': 1,  # 每月几号调整资金
            'min_pool_ratio': 0.20,  # 最小资金池比例20%（任务8修改）
            'max_pool_ratio': 0.80,  # 最大资金池比例80%（任务8修改）
            'base_pool_ratio_high': 0.70,  # 基础分配上限70%（任务8新增）
            'base_pool_ratio_low': 0.60,  # 基础分配下限60%（任务8新增）
            'low_score_threshold': 30.0,  # 低分阈值30分（任务8新增）
            'max_low_score_count': 2,  # 最大低分次数2次（任务8新增）
            'adjustment_frequency': 'monthly',  # 调整频率：monthly（每月）
            # ========== 任务11：调整周期配置 ==========
            'adjustment_interval_months': 1,  # 调整间隔月数（N可配置，默认为1，即每月调整）
            'min_trading_days': 20,  # 最低交易日数（默认为20）
            'last_adjustment_date': None,  # 上次调整日期
            'trading_days_since_last_adjustment': 0  # 自上次调整以来的交易日数
        }
        
        # ========== 策略统计信息 ==========
        self.strategy_stats = {}  # {strategy_id: {'performance': {}, 'trades': []}}
        
        # ========== 策略低分记录（任务8新增） ==========
        # 用于记录策略连续低分次数，超过阈值时暂停分配
        self.low_score_history = {}  # {strategy_id: {'low_score_count': int, 'last_score': float}}
        
        # ========== 全仓模式配置 ==========
        self.full_ratio_mode = False  # 是否开启全仓模式（默认关闭）
        self.full_ratio_strategy_id = None  # 使用全仓模式的策略ID
        
        log.info("[StrategyManager] 初始化完成")
    
    def register_strategy(self, strategy_id, strategy_instance, initial_ratio=0.5, full_ratio_mode=False):
        """
        注册策略到总控管理器
        
        参数:
            strategy_id: 策略唯一标识符（如 'limit_up', 'swing'）
            strategy_instance: 策略实例对象
            initial_ratio: 初始资金池比例（默认0.5，即50%）
            full_ratio_mode: 是否开启全仓模式（默认False），开启后该策略使用100%资金池
        
        返回:
            bool: 注册是否成功
        """
        try:
            # 检查strategy_id是否已存在
            if strategy_id in self.strategies:
                log.warning(f"策略 {strategy_id} 已存在，将被覆盖")
            
            # 验证initial_ratio参数
            if not (0 <= initial_ratio <= 1):
                log.error(f"策略 {strategy_id} 的初始资金池比例 {initial_ratio} 无效，必须在0~1之间")
                return False
            
            # 注册策略实例
            self.strategies[strategy_id] = strategy_instance
            
            # 初始化资金池（金额暂时为0，等待allocate_capital_pools计算）
            self.capital_pools[strategy_id] = {
                'amount': 0.0,
                'ratio': initial_ratio
            }
            
            # 添加到优先级列表末尾
            if strategy_id not in self.priority_order:
                self.priority_order.append(strategy_id)
            
            # 初始化统计信息
            self.strategy_stats[strategy_id] = {
                'performance': {},
                'trades': []
            }
            
            # 处理全仓模式
            if full_ratio_mode:
                self.full_ratio_mode = True
                self.full_ratio_strategy_id = strategy_id
                log.info(f"[StrategyManager] 注册策略 {strategy_id} 成功, 资金池比例: {initial_ratio:.2%}, 全仓模式: 开启")
            else:
                log.info(f"[StrategyManager] 注册策略 {strategy_id} 成功, 资金池比例: {initial_ratio:.2%}")
            
            return True
        
        except Exception as e:
            log.error(f"注册策略 {strategy_id} 失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            return False
    
    # ============================================================================
    # 动态资金池分配评分系统（任务2-6）
    # ============================================================================
    
    def calculate_strategy_scores(self, context):
        """
        计算各策略的综合评分（主评分方法）
        
        功能说明：
        - 收集各策略的历史绩效数据
        - 调用四个评分计算方法（收益率、胜率、风险、稳定性）
        - 应用综合得分公式：收益率40% + 胜率25% + 风险25% + 稳定性10%
        - 返回各策略的综合得分字典
        
        参数:
            context: 聚宽上下文对象
        
        返回:
            dict: {strategy_id: {'total_score': float, 'return_score': float, 
                                 'win_rate_score': float, 'risk_score': float, 
                                 'stability_score': float, 'details': dict}}
        
        评分维度说明：
        - 收益率得分（40%权重）：使用对数收益率，年化处理
        - 胜率得分（25%权重）：统计完整平仓交易，计算盈利交易占比
        - 风险得分（25%权重）：计算最大回撤和波动率（20日滚动窗口）
        - 稳定性得分（10%权重）：计算月度收益一致性和连续盈利月数
        
        日志输出：
        - 输出每个策略的详细评分信息
        - 输出综合得分计算过程
        - 输出评分结果汇总
        """
        try:
            log.info("[评分系统] 开始计算各策略的综合评分")
            
            strategy_scores = {}
            
            # 检查是否有策略需要评分
            if not self.strategies:
                log.warning("[评分系统] 没有注册的策略，无法计算评分")
                return strategy_scores
            
            # 检查全局交易统计数据是否存在
            if not hasattr(g, 'trade_stats') or 'strategy_performance' not in g.trade_stats:
                log.warning("[评分系统] 缺少策略绩效数据，无法计算评分")
                return strategy_scores
            
            # ========== 遍历所有策略，计算各维度评分 ==========
            for strategy_id in self.strategies.keys():
                try:
                    # 获取策略绩效数据
                    performance_data = g.trade_stats['strategy_performance'].get(strategy_id, {})
                    daily_returns = performance_data.get('daily_returns', [])
                    
                    # ========== 检查数据充足性 ==========
                    min_required_days = 20  # 最少需要20天的数据
                    if len(daily_returns) < min_required_days:
                        log.info(f"[评分系统] {strategy_id}: 数据不足（{len(daily_returns)}天），使用默认评分50分")
                        strategy_scores[strategy_id] = {
                            'total_score': 50.0,
                            'return_score': 50.0,
                            'win_rate_score': 50.0,
                            'risk_score': 50.0,
                            'stability_score': 50.0,
                            'details': {'data_days': len(daily_returns), 'note': '数据不足'}
                        }
                        continue
                    
                    # ========== 计算各维度评分 ==========
                    return_score = self._compute_return_score(daily_returns, context)
                    win_rate_score = self._compute_win_rate_score(performance_data)
                    risk_score = self._compute_risk_score(daily_returns)
                    stability_score = self._compute_stability_score(daily_returns, context)
                    
                    # ========== 计算综合得分 ==========
                    total_score = (
                        return_score * 0.4 +
                        win_rate_score * 0.25 +
                        risk_score * 0.25 +
                        stability_score * 0.1
                    )
                    
                    log.info(f"[评分系统] {strategy_id}: 综合得分{total_score:.2f}分 (收益率{return_score:.2f}, 胜率{win_rate_score:.2f}, 风险{risk_score:.2f}, 稳定性{stability_score:.2f})")
                    
                    # ========== 保存评分结果 ==========
                    strategy_scores[strategy_id] = {
                        'total_score': total_score,
                        'return_score': return_score,
                        'win_rate_score': win_rate_score,
                        'risk_score': risk_score,
                        'stability_score': stability_score,
                        'details': {'data_days': len(daily_returns), 'calculation_formula': f"{return_score:.2f}×0.4 + {win_rate_score:.2f}×0.25 + {risk_score:.2f}×0.25 + {stability_score:.2f}×0.1"}
                    }
                    
                except Exception as e:
                    log.error(f"[评分系统] 计算策略 {strategy_id} 评分失败: {str(e)}")
                    strategy_scores[strategy_id] = {
                        'total_score': 30.0,
                        'return_score': 30.0,
                        'win_rate_score': 30.0,
                        'risk_score': 30.0,
                        'stability_score': 30.0,
                        'details': {'error': str(e), 'note': '计算失败'}
                    }
            
            # ========== 输出评分结果汇总 ==========
            if strategy_scores:
                sorted_scores = sorted(strategy_scores.items(), key=lambda x: x[1]['total_score'], reverse=True)
                ranking_str = ' > '.join([f"{sid}({scores['total_score']:.1f}分)" for sid, scores in sorted_scores])
                log.info(f"[评分系统] 排名: {ranking_str}")
            
            return strategy_scores
        
        except Exception as e:
            log.error(f"[评分系统] 计算策略评分失败: {str(e)}")
            return {}
    
    def _compute_return_score(self, daily_returns, context):
        """
        计算收益率得分（权重40%）
        
        功能说明：
        - 使用对数收益率，避免复利偏差
        - 年化处理：便于不同周期比较
        - 区间归一化：将收益率转换为0-100分
        
        参数:
            daily_returns: 日收益率列表
            context: 聚宽上下文对象
        
        返回:
            float: 收益率得分（0-100分）
        
        评分标准：
        - 年化收益率 >= 20%: 100分
        - 年化收益率 >= 10%: 80分
        - 年化收益率 >= 0%: 60分
        - 年化收益率 >= -10%: 40分
        - 年化收益率 >= -20%: 20分
        - 年化收益率 < -20%: 0分
        
        日志输出：
        - 输出累计收益率
        - 输出年化收益率
        - 输出评分计算过程
        """
        try:
            log.info(f"[收益率评分] 开始计算收益率得分")
            
            if not daily_returns or len(daily_returns) == 0:
                log.warning(f"[收益率评分] 无日收益率数据，返回默认评分50分")
                return 50.0
            
            # ========== 计算累计收益率（使用对数收益率） ==========
            # 累计收益率 = ln(1 + r1) + ln(1 + r2) + ... + ln(1 + rn)
            # 使用log1p避免数值精度问题
            log_return_sum = np.sum(np.log1p(np.array(daily_returns)))
            cumulative_return = np.exp(log_return_sum) - 1
            
            log.info(f"[收益率评分] 累计收益率: {cumulative_return:.4%}")
            
            # ========== 计算年化收益率 ==========
            # 年化收益率 = (1 + 累计收益率)^(250/交易天数) - 1
            trading_days = len(daily_returns)
            annualized_return = (1 + cumulative_return) ** (250 / trading_days) - 1
            
            log.info(f"[收益率评分] 年化收益率: {annualized_return:.4%} (交易天数: {trading_days})")
            
            # ========== 评分计算（区间归一化到0-100分） ==========
            # 评分标准
            if annualized_return >= 0.20:  # 年化收益 >= 20%
                score = 100.0
                grade = "优秀"
            elif annualized_return >= 0.10:  # 年化收益 >= 10%
                score = 80.0 + (annualized_return - 0.10) / (0.20 - 0.10) * 20.0
                grade = "良好"
            elif annualized_return >= 0.00:  # 年化收益 >= 0%
                score = 60.0 + (annualized_return - 0.00) / (0.10 - 0.00) * 20.0
                grade = "合格"
            elif annualized_return >= -0.10:  # 年化收益 >= -10%
                score = 40.0 + (annualized_return - (-0.10)) / (0.00 - (-0.10)) * 20.0
                grade = "一般"
            elif annualized_return >= -0.20:  # 年化收益 >= -20%
                score = 20.0 + (annualized_return - (-0.20)) / (-0.10 - (-0.20)) * 20.0
                grade = "较差"
            else:  # 年化收益 < -20%
                score = 0.0
                grade = "很差"
            
            log.info(f"[收益率评分] 得分: {score:.2f}分 (等级: {grade})")
            
            return score
        
        except Exception as e:
            log.error(f"[收益率评分] 计算失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            return 50.0  # 计算失败时返回默认评分50分
    
    def _compute_win_rate_score(self, performance_data):
        """
        计算胜率得分（权重25%）
        
        功能说明：
        - 统计完整平仓的交易
        - 计算盈利交易占比
        - 阈值：胜率>50%为合格
        
        参数:
            performance_data: 策略绩效数据字典
        
        返回:
            float: 胜率得分（0-100分）
        
        评分标准：
        - 胜率 >= 70%: 100分
        - 胜率 >= 60%: 80分
        - 胜率 >= 50%: 60分（合格线）
        - 胜率 >= 40%: 40分
        - 胜率 >= 30%: 20分
        - 胜率 < 30%: 0分
        
        日志输出：
        - 输出总交易次数
        - 输出盈利交易次数
        - 输出胜率
        - 输出评分计算过程
        """
        try:
            log.info(f"[胜率评分] 开始计算胜率得分")
            
            # ========== 获取交易数据 ==========
            total_trades = performance_data.get('total_trades', 0)
            total_profit = performance_data.get('total_profit', 0.0)
            
            log.info(f"[胜率评分] 总交易次数: {total_trades}, 总盈亏: {total_profit:.2f}元")
            
            # ========== 检查是否有交易 ==========
            if total_trades == 0:
                log.warning(f"[胜率评分] 无交易记录，返回默认评分50分")
                return 50.0
            
            # ========== 计算胜率 ==========
            # 从全局交易记录中统计盈利交易次数
            profit_trades = 0
            if hasattr(g, 'trade_stats') and 'trade_details' in g.trade_stats:
                for trade in g.trade_stats['trade_details']:
                    if trade is not None and trade.get('strategy_id') == self.strategy_id:
                        if trade.get('action') == '卖出':
                            profit = trade.get('profit', 0)
                            if profit > 0:
                                profit_trades += 1
            
            # 如果无法从交易记录中统计，使用总盈亏近似计算
            if profit_trades == 0 and total_trades > 0:
                # 近似计算：如果总盈亏为正，假设胜率 > 50%
                if total_profit > 0:
                    win_rate = 0.55  # 假设55%胜率
                elif total_profit < 0:
                    win_rate = 0.45  # 假设45%胜率
                else:
                    win_rate = 0.50  # 假设50%胜率
                log.warning(f"[胜率评分] 无法从交易记录中统计盈利交易，使用近似胜率: {win_rate:.2%}")
            else:
                win_rate = profit_trades / total_trades if total_trades > 0 else 0.0
            
            log.info(f"[胜率评分] 盈利交易: {profit_trades}次, 总交易: {total_trades}次, 胜率: {win_rate:.2%}")
            
            # ========== 评分计算（区间归一化到0-100分） ==========
            # 评分标准
            if win_rate >= 0.70:  # 胜率 >= 70%
                score = 100.0
                grade = "优秀"
            elif win_rate >= 0.60:  # 胜率 >= 60%
                score = 80.0 + (win_rate - 0.60) / (0.70 - 0.60) * 20.0
                grade = "良好"
            elif win_rate >= 0.50:  # 胜率 >= 50%（合格线）
                score = 60.0 + (win_rate - 0.50) / (0.60 - 0.50) * 20.0
                grade = "合格"
            elif win_rate >= 0.40:  # 胜率 >= 40%
                score = 40.0 + (win_rate - 0.40) / (0.50 - 0.40) * 20.0
                grade = "一般"
            elif win_rate >= 0.30:  # 胜率 >= 30%
                score = 20.0 + (win_rate - 0.30) / (0.40 - 0.30) * 20.0
                grade = "较差"
            else:  # 胜率 < 30%
                score = 0.0
                grade = "很差"
            
            log.info(f"[胜率评分] 得分: {score:.2f}分 (等级: {grade})")
            
            return score
        
        except Exception as e:
            log.error(f"[胜率评分] 计算失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            return 50.0  # 计算失败时返回默认评分50分
    
    def _compute_risk_score(self, daily_returns):
        """
        计算风险得分（权重25%）
        
        功能说明：
        - 计算最大回撤：越小得分越高
        - 计算波动率：标准差越低越好
        - 使用20日滚动窗口
        
        参数:
            daily_returns: 日收益率列表
        
        返回:
            float: 风险得分（0-100分）
        
        评分标准：
        - 最大回撤 <= 5% 且 波动率 <= 10%: 100分
        - 最大回撤 <= 10% 且 波动率 <= 15%: 80分
        - 最大回撤 <= 15% 且 波动率 <= 20%: 60分（合格线）
        - 最大回撤 <= 20% 且 波动率 <= 25%: 40分
        - 最大回撤 <= 25% 且 波动率 <= 30%: 20分
        - 最大回撤 > 25% 或 波动率 > 30%: 0分
        
        日志输出：
        - 输出最大回撤
        - 输出波动率
        - 输出评分计算过程
        """
        try:
            log.info(f"[风险评分] 开始计算风险得分")
            
            if not daily_returns or len(daily_returns) < 10:
                log.warning(f"[风险评分] 日收益率数据不足（需要至少10天），返回默认评分50分")
                return 50.0
            
            # ========== 计算波动率（年化） ==========
            # 波动率 = 标准差 * sqrt(250)
            volatility = np.std(daily_returns) * np.sqrt(250)
            
            log.info(f"[风险评分] 年化波动率: {volatility:.4%}")
            
            # ========== 计算最大回撤 ==========
            # 累计收益序列
            cumulative_returns = np.cumprod(1 + np.array(daily_returns))
            # 滚动最大值
            running_max = np.maximum.accumulate(cumulative_returns)
            # 回撤序列
            drawdown = (cumulative_returns - running_max) / running_max
            # 最大回撤（取最小值）
            max_drawdown = np.min(drawdown)
            
            log.info(f"[风险评分] 最大回撤: {max_drawdown:.4%}")
            
            # ========== 评分计算（区间归一化到0-100分） ==========
            # 评分标准：综合考虑最大回撤和波动率
            
            # 将最大回撤转换为正向指标（回撤越小越好）
            drawdown_score = 0.0
            if max_drawdown <= -0.05:  # 最大回撤 <= 5%
                drawdown_score = 100.0
            elif max_drawdown <= -0.10:  # 最大回撤 <= 10%
                drawdown_score = 80.0 + (max_drawdown - (-0.10)) / (-0.05 - (-0.10)) * 20.0
            elif max_drawdown <= -0.15:  # 最大回撤 <= 15%
                drawdown_score = 60.0 + (max_drawdown - (-0.15)) / (-0.10 - (-0.15)) * 20.0
            elif max_drawdown <= -0.20:  # 最大回撤 <= 20%
                drawdown_score = 40.0 + (max_drawdown - (-0.20)) / (-0.15 - (-0.20)) * 20.0
            elif max_drawdown <= -0.25:  # 最大回撤 <= 25%
                drawdown_score = 20.0 + (max_drawdown - (-0.25)) / (-0.20 - (-0.25)) * 20.0
            else:  # 最大回撤 > 25%
                drawdown_score = 0.0
            
            # 将波动率转换为正向指标（波动率越小越好）
            volatility_score = 0.0
            if volatility <= 0.10:  # 波动率 <= 10%
                volatility_score = 100.0
            elif volatility <= 0.15:  # 波动率 <= 15%
                volatility_score = 80.0 + (volatility - 0.15) / (0.10 - 0.15) * 20.0
            elif volatility <= 0.20:  # 波动率 <= 20%
                volatility_score = 60.0 + (volatility - 0.20) / (0.15 - 0.20) * 20.0
            elif volatility <= 0.25:  # 波动率 <= 25%
                volatility_score = 40.0 + (volatility - 0.25) / (0.20 - 0.25) * 20.0
            elif volatility <= 0.30:  # 波动率 <= 30%
                volatility_score = 20.0 + (volatility - 0.30) / (0.25 - 0.30) * 20.0
            else:  # 波动率 > 30%
                volatility_score = 0.0
            
            # 综合得分 = 最大回撤得分 × 0.6 + 波动率得分 × 0.4
            score = drawdown_score * 0.6 + volatility_score * 0.4
            
            log.info(f"[风险评分] 最大回撤得分: {drawdown_score:.2f}分, 波动率得分: {volatility_score:.2f}分")
            log.info(f"[风险评分] 综合得分: {score:.2f}分 (计算公式: {drawdown_score:.2f}×0.6 + {volatility_score:.2f}×0.4)")
            
            return score
        
        except Exception as e:
            log.error(f"[风险评分] 计算失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            return 50.0  # 计算失败时返回默认评分50分
    
    def _compute_stability_score(self, daily_returns, context):
        """
        计算稳定性得分（权重10%）
        
        功能说明：
        - 计算月度收益一致性
        - 计算连续盈利月数
        
        参数:
            daily_returns: 日收益率列表
            context: 聚宽上下文对象
        
        返回:
            float: 稳定性得分（0-100分）
        
        评分标准：
        - 连续盈利月数 >= 3 且 月度收益标准差 <= 2%: 100分
        - 连续盈利月数 >= 2 且 月度收益标准差 <= 3%: 80分
        - 连续盈利月数 >= 1 且 月度收益标准差 <= 4%: 60分（合格线）
        - 连续盈利月数 >= 0 且 月度收益标准差 <= 5%: 40分
        - 月度收益标准差 <= 6%: 20分
        - 月度收益标准差 > 6%: 0分
        
        日志输出：
        - 输出月度收益标准差
        - 输出连续盈利月数
        - 输出评分计算过程
        """
        try:
            log.info(f"[稳定性评分] 开始计算稳定性得分")
            
            if not daily_returns or len(daily_returns) < 20:
                log.warning(f"[稳定性评分] 日收益率数据不足（需要至少20天），返回默认评分50分")
                return 50.0
            
            # ========== 转换为月度收益率 ==========
            # 假设每个月约20个交易日
            daily_returns_array = np.array(daily_returns)
            monthly_returns = []
            
            # 按月分组（简单假设每20天为一个月）
            for i in range(0, len(daily_returns_array), 20):
                month_data = daily_returns_array[i:i+20]
                if len(month_data) > 0:
                    # 月度收益率 = (1 + 日收益率1) × (1 + 日收益率2) × ... - 1
                    month_return = np.prod(1 + month_data) - 1
                    monthly_returns.append(month_return)
            
            log.info(f"[稳定性评分] 月度收益率数量: {len(monthly_returns)}")
            
            if len(monthly_returns) < 2:
                log.warning(f"[稳定性评分] 月度收益率数据不足（需要至少2个月），返回默认评分50分")
                return 50.0
            
            # ========== 计算月度收益标准差 ==========
            monthly_std = np.std(monthly_returns)
            
            log.info(f"[稳定性评分] 月度收益标准差: {monthly_std:.4%}")
            
            # ========== 计算连续盈利月数 ==========
            consecutive_profit_months = 0
            for monthly_return in reversed(monthly_returns):  # 从最近月份开始
                if monthly_return > 0:
                    consecutive_profit_months += 1
                else:
                    break
            
            log.info(f"[稳定性评分] 连续盈利月数: {consecutive_profit_months}个月")
            
            # ========== 评分计算（区间归一化到0-100分） ==========
            # 月度收益标准差评分
            std_score = 0.0
            if monthly_std <= 0.02:  # 标准差 <= 2%
                std_score = 100.0
            elif monthly_std <= 0.03:  # 标准差 <= 3%
                std_score = 80.0 + (monthly_std - 0.03) / (0.02 - 0.03) * 20.0
            elif monthly_std <= 0.04:  # 标准差 <= 4%
                std_score = 60.0 + (monthly_std - 0.04) / (0.03 - 0.04) * 20.0
            elif monthly_std <= 0.05:  # 标准差 <= 5%
                std_score = 40.0 + (monthly_std - 0.05) / (0.04 - 0.05) * 20.0
            elif monthly_std <= 0.06:  # 标准差 <= 6%
                std_score = 20.0 + (monthly_std - 0.06) / (0.05 - 0.06) * 20.0
            else:  # 标准差 > 6%
                std_score = 0.0
            
            # 连续盈利月数评分
            profit_months_score = 0.0
            if consecutive_profit_months >= 3:  # 连续盈利 >= 3个月
                profit_months_score = 100.0
            elif consecutive_profit_months >= 2:  # 连续盈利 >= 2个月
                profit_months_score = 80.0
            elif consecutive_profit_months >= 1:  # 连续盈利 >= 1个月
                profit_months_score = 60.0
            else:  # 无连续盈利
                profit_months_score = 40.0
            
            # 综合得分 = 月度收益标准差得分 × 0.7 + 连续盈利月数得分 × 0.3
            score = std_score * 0.7 + profit_months_score * 0.3
            
            log.info(f"[稳定性评分] 标准差得分: {std_score:.2f}分, 连续盈利月数得分: {profit_months_score:.2f}分")
            log.info(f"[稳定性评分] 综合得分: {score:.2f}分 (计算公式: {std_score:.2f}×0.7 + {profit_months_score:.2f}×0.3)")
            
            return score
        
        except Exception as e:
            log.error(f"[稳定性评分] 计算失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            return 50.0  # 计算失败时返回默认评分50分
    
    # ============================================================================
    # 动态资金池分配评分系统结束
    # ============================================================================
    
    def allocate_capital_pools(self, context):
        """
        资金池分配计算
        
        根据量化因子（收益率、波动率、夏普比率、最大回撤）动态分配各策略资金池
        如果开启全仓模式，则让指定策略使用100%资金池
        
        参数:
            context: 策略上下文对象
        
        返回:
            bool: 分配是否成功
        
        量化因子说明:
            - 收益率权重40%
            - 夏普比率权重30%
            - 最大回撤权重30%
        
        限制条件:
            - 单个策略资金池占比: 5%~95%
            - 资金池平滑过渡，避免频繁调整
        
        全仓模式说明:
            - 当full_ratio_mode开启时，full_ratio_strategy_id策略使用100%资金池
            - 其他策略资金池为0%
            - 跳过资金池动态调整逻辑
        """
        try:
            # 检查是否有策略需要分配
            if not self.strategies:
                log.warning("没有注册的策略，跳过资金池分配")
                return False
            
            # 获取账户总资金
            total_capital = context.portfolio.total_value
            
            # ========== 全仓模式检查 ==========
            if self.full_ratio_mode and self.full_ratio_strategy_id:
                log.info(f"[资金池] 全仓模式已开启，策略 {self.full_ratio_strategy_id} 使用100%资金池")
                
                # 全仓策略使用100%资金池
                for strategy_id in self.strategies.keys():
                    if strategy_id == self.full_ratio_strategy_id:
                        self.capital_pools[strategy_id]['ratio'] = 1.0
                        self.capital_pools[strategy_id]['amount'] = total_capital
                    else:
                        self.capital_pools[strategy_id]['ratio'] = 0.0
                        self.capital_pools[strategy_id]['amount'] = 0.0
                
                # 输出分配结果
                allocation_str = ', '.join([f"{sid}: {pool['ratio']:.0%}" for sid, pool in self.capital_pools.items()])
                log.info(f"[资金池] 分配完成（全仓模式）: {allocation_str}")
                return True
            
            # ========== 调用新的评分系统 ==========
            log.info("[资金池] 开始计算策略评分（使用新的四维度评分系统）")
            strategy_score_results = self.calculate_strategy_scores(context)
            
            if not strategy_score_results:
                log.warning("[资金池] 评分系统返回空结果，使用初始比例分配")
                for strategy_id, pool in self.capital_pools.items():
                    initial_ratio = pool.get('ratio', 0.5)
                    pool['ratio'] = initial_ratio
                    pool['amount'] = total_capital * initial_ratio
                return True
            
            # 提取综合得分
            strategy_scores = {
                strategy_id: scores['total_score']
                for strategy_id, scores in strategy_score_results.items()
            }
            
            log.info(f"[资金池] 策略综合得分: {strategy_scores}")
            
            # 根据评分分配资金池
            if strategy_scores:
                # 转换为列表后再求和
                total_score = float(sum(list(strategy_scores.values())))
            else:
                total_score = 0.0
            
            if not strategy_scores or total_score <= 0:
                # 所有评分为0或负数，或没有策略评分，根据策略优先级分配资金池
                # 输出当前优先级顺序
                if not self.priority_order:
                    log.warning("[资金池] 策略优先级未设置，使用初始比例")
                    for strategy_id, pool in self.capital_pools.items():
                        initial_ratio = pool.get('ratio', 0.5)
                        pool['ratio'] = initial_ratio
                    return True
                
                # 根据优先级分配资金池（测试阶段使用简单权重）
                # 优先级1：70%，优先级2：30%
                strategy_count = len(self.priority_order)
                if strategy_count >= 2:
                    # 至少有两个策略时使用优先级分配
                    for idx, strategy_id in enumerate(self.priority_order):
                        if idx == 0:
                            # 优先级1分配70%
                            ratio = 0.7
                        elif idx == 1:
                            # 优先级2分配30%
                            ratio = 0.3
                        else:
                            # 更多策略时平分剩余部分（如果有）
                            remaining_ratio = 1.0 - (0.7 + 0.3 * min(1, idx))
                            ratio = remaining_ratio / max(1, strategy_count - idx)
                        
                        self.capital_pools[strategy_id]['ratio'] = ratio
                else:
                    # 只有一个策略时，分配100%
                    strategy_id = self.priority_order[0] if self.priority_order else list(self.strategies.keys())[0]
                    self.capital_pools[strategy_id]['ratio'] = 1.0
            else:
                # ========== 根据评分应用资金分配规则（任务8） ==========
                log.info("[资金池] 开始应用资金分配规则")
                
                # ========== 步骤1：检查策略连续低分情况（极端情况处理） ==========
                suspended_strategies = []  # 暂停分配的策略列表
                
                for strategy_id, scores in strategy_score_results.items():
                    current_score = scores['total_score']
                    low_score_threshold = self.allocation_config['low_score_threshold']
                    
                    # 初始化低分记录
                    if strategy_id not in self.low_score_history:
                        self.low_score_history[strategy_id] = {
                            'low_score_count': 0,
                            'last_score': current_score
                        }
                    
                    # 检查是否为低分
                    if current_score < low_score_threshold:
                        self.low_score_history[strategy_id]['low_score_count'] += 1
                        self.low_score_history[strategy_id]['last_score'] = current_score
                        
                        low_score_count = self.low_score_history[strategy_id]['low_score_count']
                        max_low_score_count = self.allocation_config['max_low_score_count']
                        
                        log.warning(f"[资金池] 策略 {strategy_id} 连续第{low_score_count}次低分（得分: {current_score:.2f}分 < {low_score_threshold}分阈值）")
                        
                        # 检查是否超过阈值
                        if low_score_count >= max_low_score_count:
                            suspended_strategies.append(strategy_id)
                            log.warning(f"[资金池] 策略 {strategy_id} 连续{low_score_count}次低分，暂停分配！")
                    else:
                        # 重置低分计数
                        if self.low_score_history[strategy_id]['low_score_count'] > 0:
                            log.info(f"[资金池] 策略 {strategy_id} 得分恢复（{current_score:.2f}分），重置低分计数")
                        self.low_score_history[strategy_id]['low_score_count'] = 0
                        self.low_score_history[strategy_id]['last_score'] = current_score
                
                # ========== 步骤2：应用基础分配规则（表现好的策略获得60-70%资金） ==========
                # 找出得分最高的策略
                sorted_strategies = sorted(strategy_scores.items(), key=lambda x: x[1], reverse=True)
                
                if len(sorted_strategies) >= 2:
                    # 至少有两个策略，应用基础分配规则
                    best_strategy_id = sorted_strategies[0][0]
                    second_best_strategy_id = sorted_strategies[1][0]
                    
                    # 基础分配：最佳策略获得60-70%，根据得分差异调整
                    best_score = float(strategy_scores[best_strategy_id])
                    second_best_score = float(strategy_scores[second_best_strategy_id])
                    score_diff = best_score - second_best_score
                    
                    # 得分差异越大，最佳策略分配比例越高
                    if score_diff > 20:
                        # 得分差异很大，最佳策略获得70%
                        best_ratio = float(self.allocation_config['base_pool_ratio_high'])
                    elif score_diff > 10:
                        # 得分差异较大，最佳策略获得65%
                        best_ratio = 0.65
                    else:
                        # 得分差异较小，最佳策略获得60%
                        best_ratio = float(self.allocation_config['base_pool_ratio_low'])
                    
                    # 第二名策略获得剩余资金
                    second_ratio = 1.0 - best_ratio
                    
                    log.info(f"[资金池] 基础分配规则: {best_strategy_id} {best_ratio:.0%}, {second_best_strategy_id} {second_ratio:.0%}（得分差异: {score_diff:.2f}分）")
                    
                    # 应用基础分配比例
                    temp_ratios = {}
                    temp_ratios[best_strategy_id] = best_ratio
                    temp_ratios[second_best_strategy_id] = second_ratio
                    
                    # 其他策略按初始比例分配（如果有）
                    for strategy_id in strategy_scores.keys():
                        if strategy_id not in temp_ratios:
                            temp_ratios[strategy_id] = 0.0  # 其他策略不分配
                else:
                    # 只有一个策略，分配100%
                    temp_ratios = {strategy_id: 1.0 for strategy_id in strategy_scores.keys()}
                    log.info(f"[资金池] 只有一个策略，分配100%资金")
                
                # ========== 步骤3：应用上下限限制（20%-80%） ==========
                min_ratio = float(self.allocation_config['min_pool_ratio'])
                max_ratio = float(self.allocation_config['max_pool_ratio'])
                
                for strategy_id in temp_ratios.keys():
                    # 检查是否暂停分配
                    if strategy_id in suspended_strategies:
                        temp_ratios[strategy_id] = min_ratio  # 暂停策略只获得最小比例
                        log.warning(f"[资金池] 策略 {strategy_id} 已暂停分配，仅分配最小比例 {min_ratio:.0%}")
                    else:
                        # 应用上下限限制
                        current_ratio = float(temp_ratios[strategy_id])
                        if current_ratio < min_ratio:
                            temp_ratios[strategy_id] = min_ratio
                            log.info(f"[资金池] 策略 {strategy_id} 分配比例低于下限，调整为 {min_ratio:.0%}")
                        elif current_ratio > max_ratio:
                            temp_ratios[strategy_id] = max_ratio
                            log.info(f"[资金池] 策略 {strategy_id} 分配比例高于上限，调整为 {max_ratio:.0%}")
                        else:
                                        temp_ratios[strategy_id] = current_ratio                            
                # ========== 步骤4：资金池平滑过渡逻辑（与上一次比例的差值不超过20%） ==========
                max_change = 0.2
                final_ratios = {}
                
                for strategy_id, new_ratio in temp_ratios.items():
                    # 确保new_ratio是float类型
                    new_ratio = float(new_ratio)
                    last_ratio = self.capital_pools.get(strategy_id, {}).get('ratio', new_ratio)
                    last_ratio = float(last_ratio)
                    
                    if abs(new_ratio - last_ratio) > max_change:
                        if new_ratio > last_ratio:
                            final_ratio = last_ratio + max_change
                        else:
                            final_ratio = last_ratio - max_change
                        log.info(f"[资金池] 策略 {strategy_id} 平滑过渡: {last_ratio:.0%} → {final_ratio:.0%}（目标: {new_ratio:.0%}）")
                    else:
                        final_ratio = new_ratio
                    
                    final_ratios[strategy_id] = float(final_ratio)                            
                # ========== 步骤5：归一化比例 ==========
                total_ratio = sum(float(final_ratios[strategy_id]) for strategy_id in final_ratios.keys())
                
                if abs(total_ratio - 1.0) > 0.01:
                    log.info(f"[资金池] 总比例不等于1 ({total_ratio:.4f})，进行归一化")
                    for strategy_id in final_ratios.keys():
                        final_ratios[strategy_id] = float(final_ratios[strategy_id]) / total_ratio
                
                # ========== 步骤6：应用最终分配比例 ==========
                for strategy_id, ratio in final_ratios.items():
                    self.capital_pools[strategy_id]['ratio'] = float(ratio)            # 计算实际资金池金额
            total_ratio = sum(pool['ratio'] for pool in self.capital_pools.values())
            
            # 如果总比例不等于1，进行归一化
            if abs(total_ratio - 1.0) > 0.01:
                for strategy_id, pool in self.capital_pools.items():
                    pool['ratio'] = pool['ratio'] / total_ratio
            
            # 计算实际金额
            for strategy_id, pool in self.capital_pools.items():
                pool['amount'] = total_capital * pool['ratio']
            
            # 输出最终分配结果（简化版）
            allocation_str = ', '.join([f"{sid}: {pool['ratio']:.0%}" for sid, pool in self.capital_pools.items()])
            log.info(f"[资金池] 分配完成: {allocation_str}")
            
            # 更新分配日期
            self.allocation_config['last_allocation_date'] = context.current_dt.date()
            
            return True
        
        except Exception as e:
            log.error(f"资金池分配计算失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            return False
    
    def update_strategy_priority(self, trend):
        """
        根据市场环境更新策略优先级
        
        功能说明：
        - 根据市场趋势调整不同策略的执行优先级
        - 在不同市场环境下，优先执行适应性更好的策略
        - 更新 StrategyManager 的 priority_order 列表
        
        参数:
            trend: 市场趋势标识，可能的值：
                - 'down': 下跌市场（短期、中期、长期收益率均为负）
                - 'strong_up': 强势上涨市场（短期、中期、长期收益率均为正且大于3%）
                - 'flat': 平稳市场（收益率波动小，无明显趋势）
                - 'up': 上涨市场（短期、中期、长期收益率均为正）
                - None/其他: 默认优先级
        
        返回:
            bool: 更新是否成功
        
        策略优先级配置说明（临时测试）：
        - 下跌市场: test_strategy_2（模拟保守型）优先
        - 强势上涨市场: test_strategy_1（模拟进攻型）优先
        - 平稳市场: test_strategy_1（模拟进攻型）优先
        - 上涨市场: test_strategy_1（模拟进攻型）优先
        - 默认: test_strategy_1（模拟进攻型）优先
        
        【正式配置】后续移植实际策略后将改为：
        - 下跌市场: 小市值波段策略（swing）优先（保守型）
        - 强势上涨市场: 五合一打板策略（limit_up）优先（进攻型）
        - 平稳市场: 五合一打板策略（limit_up）优先（平衡型）
        - 上涨市场: 五合一打板策略（limit_up）优先（进攻型）
        - 默认: 五合一打板策略（limit_up）优先
        
        实现参考：
        Enhanced_5in1_LimitUp_Trading_Strategy.py 中的 update_strategy_priority 函数
        """
        try:
            # ==================== 步骤1：定义不同市场环境下的策略优先级 ====================
            if trend == 'down':
                priority_config = ['test_strategy_2', 'test_strategy_1']
                reason = "下跌市场"
            
            elif trend == 'strong_up':
                priority_config = ['test_strategy_1', 'test_strategy_2']
                reason = "强势上涨"
            
            elif trend == 'flat':
                priority_config = ['test_strategy_1', 'test_strategy_2']
                reason = "平稳市场"
            
            elif trend == 'up':
                priority_config = ['test_strategy_1', 'test_strategy_2']
                reason = "上涨市场"
            
            else:
                priority_config = ['test_strategy_1', 'test_strategy_2']
                reason = "默认"
            
            # ==================== 步骤2：过滤已注册的策略 ====================
            registered_strategies = set(self.strategies.keys())
            valid_priority = [s for s in priority_config if s in registered_strategies]
            
            if not valid_priority:
                log.warning(f"优先级配置中的策略均未注册，跳过优先级更新")
                return False
            
            # ==================== 步骤3：添加未在优先级配置中的策略 ====================
            for strategy_id in self.strategies.keys():
                if strategy_id not in valid_priority:
                    valid_priority.append(strategy_id)
            
            # ==================== 步骤4：更新优先级顺序 ====================
            self.priority_order = valid_priority
            
            # ==================== 步骤5：输出简化日志 ====================
            log.info(f"[策略优先级] {reason}: {' > '.join(self.priority_order)}")
            
            # ==================== 步骤6：存储到统计信息 ====================
            self.strategy_stats['priority'] = {
                'trend': trend,
                'priority_order': self.priority_order,
                'reason': reason,
                'update_time': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return True
        
        except Exception as e:
            log.error(f"策略优先级更新失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            return False
    
    def analyze_market_trend(self, context):
        """
        市场趋势判断函数
        
        功能说明：
        - 基于上证指数（000001.XSHG）的最近5天数据
        - 计算大盘涨跌幅、波动率、量能比
        - 根据涨跌幅判断市场趋势
        
        参数:
            context: 策略上下文对象
        
        返回:
            dict: 市场趋势信息，包含：
                - trend: 趋势标识（'strong_up', 'up', 'flat', 'down'）
                - change_rate: 涨跌幅（%）
                - volatility: 波动率（%）
                - volume_ratio: 量能比
                - date: 分析日期
        
        市场趋势判断标准：
        - strong_up（强势上涨）: 大盘涨幅 > 1%
        - up（上涨）: 大盘涨幅 > 0% 且 ≤ 1%
        - flat（平稳）: 大盘涨幅 > -1% 且 ≤ 0%
        - down（下跌）: 大盘跌幅 ≤ -1%
        
        实现参考：
        Enhanced_5in1_LimitUp_Trading_Strategy.py 中的 record_morning_stats 函数
        """
        try:
            # ==================== 步骤1：获取上证指数数据 ====================
            index_code = '000001.XSHG'  # 上证指数
            
            # 获取最近5个交易日的数据
            index_data = get_price(
                index_code,
                end_date=context.previous_date,  # 使用昨日数据避免未来数据
                count=5,
                frequency='daily',
                fields=['close', 'volume'],
                panel=False
            )
            
            if index_data is None or index_data.empty or len(index_data) < 2:
                log.warning(f"未能获取 {index_code} 的足够数据，使用默认趋势 'flat'")
                return {
                    'trend': 'flat',
                    'change_rate': 0.0,
                    'volatility': 0.0,
                    'volume_ratio': 1.0,
                    'date': context.current_dt.strftime('%Y-%m-%d'),
                    'note': '数据不足，使用默认趋势'
                }
            
            # ==================== 步骤2：计算涨跌幅 ====================
            current_close = float(index_data['close'].iloc[-1])
            prev_close = float(index_data['close'].iloc[-2])
            change_rate = (current_close - prev_close) / prev_close * 100
            
            # ==================== 步骤3：计算波动率 ====================
            volatility = float(index_data['close'].pct_change().std() * 100)
            
            # ==================== 步骤4：计算量能比 ====================
            current_volume = float(index_data['volume'].iloc[-1])
            avg_volume = float(index_data['volume'].head(-1).mean())
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            # ==================== 步骤5：判断市场趋势 ====================
            if change_rate > 1:
                trend = "strong_up"
                trend_desc = "强势上涨"
            elif change_rate > 0:
                trend = "up"
                trend_desc = "上涨"
            elif change_rate > -1:
                trend = "flat"
                trend_desc = "平稳"
            else:
                trend = "down"
                trend_desc = "下跌"
            
            # ==================== 步骤6：输出分析结果 ====================
            log.info(f"[市场趋势] {trend_desc} ({change_rate:+.2f}%), 波动率: {volatility:.2f}%, 量能比: {volume_ratio:.2f}")
            
            # ==================== 步骤7：存储到全局统计 ====================
            if not hasattr(g, 'trade_stats'):
                g.trade_stats = {}
            
            g.trade_stats['market_stats'] = {
                'date': context.current_dt.strftime('%Y-%m-%d'),
                'trend': trend,
                'trend_desc': trend_desc,
                'change_rate': change_rate,
                'volatility': volatility,
                'volume_ratio': volume_ratio,
                'index_code': index_code,
                'index_close': current_close
            }
            
            return {
                'trend': trend,
                'trend_desc': trend_desc,
                'change_rate': change_rate,
                'volatility': volatility,
                'volume_ratio': volume_ratio,
                'date': context.current_dt.strftime('%Y-%m-%d'),
                'index_code': index_code,
                'index_close': current_close
            }
        
        except Exception as e:
            log.error(f"市场趋势分析失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            
            # 返回默认趋势
            return {
                'trend': 'flat',
                'trend_desc': '平稳',
                'change_rate': 0.0,
                'volatility': 0.0,
                'volume_ratio': 1.0,
                'date': context.current_dt.strftime('%Y-%m-%d'),
                'note': f'分析失败: {str(e)}'
            }

    # ============================================================================
    # 买卖冲突避免机制（safe_order函数）
    # ============================================================================
    
    def safe_order(self, context: Any, stock: str, amount: float, strategy_id: str, order_type: str = 'order', **kwargs) -> Dict[str, Any]:
        """
        安全下单函数（买卖冲突避免机制）
        
        参数:
            context: 策略上下文对象
            stock: 股票代码
            amount: 下单数量或金额
            strategy_id: 策略唯一标识符
            order_type: 下单方式（'order'/'order_value'/'order_target_value'/'order_target'）
            **kwargs: 额外参数
        
        返回:
            dict: {'success': bool, 'order_id': 订单ID, 'message': 结果消息}
        """
        try:
            # ========== 步骤1：参数验证 ==========
            if not stock:
                log.warning(f"[{strategy_id}] safe_order: 股票代码为空，跳过下单")
                return {'success': False, 'order_id': None, 'message': '股票代码为空'}
            
            if strategy_id not in self.strategies:
                log.warning(f"[{strategy_id}] safe_order: 策略未注册，跳过下单")
                return {'success': False, 'order_id': None, 'message': '策略未注册'}
            
            # ========== 步骤2：判断买卖方向 ==========
            is_buy = True  # 默认为买入
            
            if order_type == 'order':
                # 按数量下单：amount为股数，正数买入，负数卖出
                is_buy = amount > 0
            elif order_type == 'order_value':
                # 按金额下单：amount为金额，正数买入，负数卖出
                is_buy = amount > 0
            elif order_type == 'order_target_value':
                # 目标市值下单：需要计算当前持仓和目标市值的差值
                position = context.portfolio.positions.get(stock)
                current_value = position.total_amount * position.price if position and position.total_amount > 0 else 0
                is_buy = amount > current_value
            elif order_type == 'order_target':
                # 目标数量下单：需要计算当前持仓和目标数量的差值
                position = context.portfolio.positions.get(stock)
                current_amount = position.total_amount if position else 0
                is_buy = amount > current_amount
            else:
                log.warning(f"[{strategy_id}] safe_order: 不支持的order_type '{order_type}'，跳过下单")
                return {'success': False, 'order_id': None, 'message': f'不支持的order_type: {order_type}'}
            
            action = '买入' if is_buy else '卖出'
            
            # ========== 步骤3：策略标签检查逻辑 ==========
            # 检查股票是否属于当前策略，防止策略间买卖冲突
            
            # 检查g.strategy_tags是否存在
            if not hasattr(g, 'strategy_tags'):
                g.strategy_tags = {}
            
            # 检查g.strategy_positions是否存在
            if not hasattr(g, 'strategy_positions'):
                g.strategy_positions = {}
            
            if is_buy:
                # ========== 买入操作检查 ==========
                # 检查股票是否已被其他策略持有
                if stock in g.strategy_tags:
                    owner_strategy = g.strategy_tags[stock]
                    
                    # 如果股票已被其他策略持有，拒绝买入（防止冲突）
                    if owner_strategy != strategy_id:
                        log.warning(f"[{strategy_id}] safe_order: 股票 {stock} 已被策略 {owner_strategy} 持有，拒绝买入以避免冲突")
                        return {
                            'success': False,
                            'order_id': None,
                            'message': f'股票已被策略 {owner_strategy} 持有，无法买入'
                        }
                    else:
                        # 同一策略持有该股票，允许加仓
                        log.debug(f"[{strategy_id}] safe_order: 股票 {stock} 已被当前策略持有，允许加仓")
                else:
                    # 股票未被任何策略持有，允许买入
                    log.debug(f"[{strategy_id}] safe_order: 股票 {stock} 未被任何策略持有，允许买入")
            
            else:
                # ========== 卖出操作检查 ==========
                # 检查股票是否属于当前策略
                if stock in g.strategy_tags:
                    owner_strategy = g.strategy_tags[stock]
                    
                    # 如果股票不属于当前策略，拒绝卖出（防止冲突）
                    if owner_strategy != strategy_id:
                        log.warning(f"[{strategy_id}] safe_order: 股票 {stock} 属于策略 {owner_strategy}，当前策略 {strategy_id} 无法卖出")
                        return {
                            'success': False,
                            'order_id': None,
                            'message': f'股票属于策略 {owner_strategy}，无法卖出'
                        }
                    else:
                        # 股票属于当前策略，允许卖出
                        log.debug(f"[{strategy_id}] safe_order: 股票 {stock} 属于当前策略，允许卖出")
                else:
                    # 股票未被任何策略持有，允许卖出（可能是手动操作或特殊情况）
                    log.warning(f"[{strategy_id}] safe_order: 股票 {stock} 未被任何策略持有，允许卖出（无标签）")
            
            # ========== 步骤3完成 ==========
            # 策略标签检查通过，继续执行买卖操作
            
            # ========== 步骤4：资金池验证（买入时） ==========
            if is_buy:
                # 获取策略资金池
                strategy_pool = self.capital_pools.get(strategy_id, {})
                available_capital = strategy_pool.get('amount', 0)
                
                # 计算需要的资金
                if order_type == 'order':
                    # 按数量下单，计算所需金额
                    current_data = get_current_data()
                    if stock in current_data:
                        price = current_data[stock].last_price
                        required_capital = abs(amount) * price
                    else:
                        log.warning(f"[{strategy_id}] safe_order: 无法获取 {stock} 的当前价格")
                        required_capital = float('inf')
                elif order_type == 'order_value':
                    # 按金额下单
                    required_capital = abs(amount)
                elif order_type == 'order_target_value':
                    # 目标市值下单，计算所需金额
                    position = context.portfolio.positions.get(stock)
                    current_value = position.total_amount * position.price if position and position.total_amount > 0 else 0
                    required_capital = abs(amount - current_value)
                elif order_type == 'order_target':
                    # 目标数量下单，计算所需金额
                    position = context.portfolio.positions.get(stock)
                    current_amount = position.total_amount if position else 0
                    current_data = get_current_data()
                    if stock in current_data:
                        price = current_data[stock].last_price
                        required_capital = abs(amount - current_amount) * price
                    else:
                        log.warning(f"[{strategy_id}] safe_order: 无法获取 {stock} 的当前价格")
                        required_capital = float('inf')
                else:
                    required_capital = float('inf')
                
                # 检查资金池是否充足
                if required_capital > available_capital:
                    log.warning(f"[{strategy_id}] safe_order: 资金池不足（需要{required_capital:.2f}元，可用{available_capital:.2f}元）")
                    return {'success': False, 'order_id': None, 'message': '资金池不足'}
            
            # ========== 步骤5：执行下单 ==========
            order_id = None
            order_message = ''
            
            # ✅ 修复：在下单前先保存持仓成本信息（用于卖出盈亏计算）
            # 避免下单后持仓被清空导致无法计算盈亏
            # 注意：必须深拷贝关键属性，避免引用被修改
            position_cost_info = None  # 改名为更清晰的变量名
            if not is_buy:
                # 卖出操作前保存持仓成本信息（深拷贝关键属性）
                position = context.portfolio.positions.get(stock)
                if position and position.total_amount > 0:
                    position_cost_info = {
                        'avg_cost': position.avg_cost,
                        'total_amount': position.total_amount,
                        'cost_value': position.avg_cost * position.total_amount
                    }
                    log.debug(f"[{strategy_id}] safe_order: 卖出前保存持仓信息 - 成本价:{position_cost_info['avg_cost']:.2f}, 数量:{position_cost_info['total_amount']:.0f}")
            
            try:
                if order_type == 'order':
                    # 按数量下单
                    order_id = order(stock, amount, **kwargs)
                    order_message = f'按数量{action} {amount:.0f}股'
                
                elif order_type == 'order_value':
                    # 按金额下单
                    order_id = order_value(stock, amount, **kwargs)
                    order_message = f'按金额{action} {amount:.2f}元'
                
                elif order_type == 'order_target_value':
                    # 目标市值下单
                    order_id = order_target_value(stock, amount, **kwargs)
                    order_message = f'目标市值调整为 {amount:.2f}元'
                
                elif order_type == 'order_target':
                    # 目标数量下单
                    order_id = order_target(stock, amount, **kwargs)
                    order_message = f'目标数量调整为 {amount:.0f}股'
                
            except Exception as e:
                log.error(f"[{strategy_id}] safe_order: 下单失败 - {str(e)}")
                return {'success': False, 'order_id': None, 'message': f'下单失败: {str(e)}'}
            
            # ========== 步骤6：记录买卖日志 ==========
            if order_id:
                # 下单成功，记录详细信息
                log.info(f"[{strategy_id}] safe_order: {order_message} 成功 - {stock} (订单ID: {order_id})")

                # ========== 获取成交信息 ==========
                try:
                    # 聚宽平台的order_value/order/order_target_value等下单函数返回的是UserOrder对象
                    # UserOrder对象包含以下属性：order_id, security, amount, filled, price, status等
                    # 直接从order_id对象中提取成交信息
                    filled_amount = 0
                    avg_price = 0.0
                    filled_value = 0.0

                    if order_id is not None:
                        # 尝试从UserOrder对象中提取成交信息
                        filled_amount = getattr(order_id, 'filled', 0)  # 已成交数量
                        avg_price = getattr(order_id, 'price', 0)  # 成交价格
                        filled_value = filled_amount * avg_price  # 成交金额

                        if filled_amount > 0 and avg_price > 0:
                            # 成功提取成交信息
                            log.debug(f"[{strategy_id}] safe_order: 成交信息 - 数量:{filled_amount:.0f}股, 价格:{avg_price:.2f}元, 金额:{filled_value:.2f}元")
                        else:
                            # UserOrder对象中成交信息为0或无效，使用预估信息
                            log.debug(f"[{strategy_id}] safe_order: UserOrder对象成交信息为空（filled={filled_amount}, price={avg_price}），使用预估信息")

                            # 获取当前价格作为预估成交价
                            current_data = get_current_data()
                            if stock in current_data:
                                avg_price = current_data[stock].last_price
                            else:
                                avg_price = 0.0

                            # 根据order_type计算预估成交数量和金额
                            if order_type == 'order':
                                # 按数量下单
                                filled_amount = abs(amount)
                            elif order_type == 'order_value':
                                # 按金额下单
                                filled_amount = abs(amount) / avg_price if avg_price > 0 else 0
                            elif order_type == 'order_target_value':
                                # 目标市值下单
                                position = context.portfolio.positions.get(stock)
                                current_value = position.total_amount * position.price if position and position.total_amount > 0 else 0
                                if amount > current_value:
                                    filled_amount = (amount - current_value) / avg_price if avg_price > 0 else 0
                                else:
                                    filled_amount = 0  # 卖出
                            elif order_type == 'order_target':
                                # 目标数量下单
                                position = context.portfolio.positions.get(stock)
                                current_amount = position.total_amount if position else 0
                                filled_amount = abs(amount - current_amount)
                            else:
                                filled_amount = 0

                            filled_value = filled_amount * avg_price
                            log.debug(f"[{strategy_id}] safe_order: 预估成交信息 - 数量:{filled_amount:.0f}股, 价格:{avg_price:.2f}元, 金额:{filled_value:.2f}元")
                    else:
                        log.warning(f"[{strategy_id}] safe_order: order_id为None，无法获取成交信息")
                        filled_amount = 0
                        avg_price = 0.0
                        filled_value = 0.0

                except Exception as e:
                    # 获取订单信息失败，使用默认值
                    log.warning(f"[{strategy_id}] safe_order: 获取订单信息失败: {str(e)}，使用默认值")
                    filled_amount = 0
                    avg_price = 0.0
                    filled_value = 0.0
                
                # ========== 构建交易记录 ==========
                # 提取订单ID（UserOrder对象中的order_id属性）
                actual_order_id = getattr(order_id, 'order_id', str(order_id)) if order_id else None

                trade_record = {
                    'stock': stock,
                    'action': action,  # '买入' 或 '卖出'
                    'order_id': actual_order_id,  # 使用实际的订单ID
                    'order_type': order_type,
                    'amount': filled_amount,  # 成交数量（股）
                    'price': avg_price,  # 成交价格
                    'value': filled_value,  # 成交金额（元）
                    'strategy_id': strategy_id,
                    'timestamp': transform_date(context.current_dt, 'str_yyyy_mm_dd_hh_mm_ss'),
                    'message': order_message,
                    'reason': order_message  # 添加reason字段，与log_daily_trades函数保持一致
                }
                
                # ========== 卖出时计算盈亏 ==========
                if not is_buy and filled_amount > 0:
                    try:
                        # ✅ 修复：使用下单前深拷贝的持仓成本信息
                        if position_cost_info and position_cost_info['total_amount'] > 0:
                            # 计算盈亏
                            avg_cost = position_cost_info['avg_cost']
                            total_amount = position_cost_info['total_amount']
                            cost_value = position_cost_info['cost_value']
                            
                            # 计算卖出盈亏
                            profit = filled_value - cost_value
                            profit_pct = (profit / cost_value * 100) if cost_value > 0 else 0
                            
                            # 添加盈亏信息到交易记录
                            trade_record['profit'] = profit
                            trade_record['profit_pct'] = profit_pct
                            trade_record['avg_cost'] = avg_cost
                            trade_record['cost_value'] = cost_value
                            
                            # 记录盈亏信息
                            log.info(f"[{strategy_id}] safe_order: 卖出盈亏 - "
                                   f"成本:{avg_cost:.2f}元/股, 成本总额:{cost_value:.2f}元, "
                                   f"成交:{avg_price:.2f}元/股, 成交总额:{filled_value:.2f}元, "
                                   f"盈亏:{profit:+.2f}元 ({profit_pct:+.2f}%)")
                        else:
                            # 无持仓信息，无法计算盈亏
                            trade_record['profit'] = 0
                            trade_record['profit_pct'] = 0.0
                            log.warning(f"[{strategy_id}] safe_order: 无持仓信息，无法计算盈亏")
                    except Exception as e:
                        log.error(f"[{strategy_id}] safe_order: 计算卖出盈亏失败: {str(e)}")
                        trade_record['profit'] = 0
                        trade_record['profit_pct'] = 0.0
                
                # ========== 添加到全局交易记录 ==========
                if not hasattr(g, 'today_trades'):
                    g.today_trades = []
                
                g.today_trades.append(trade_record)
                log.debug(f"[{strategy_id}] safe_order: 交易记录已添加到 g.today_trades")
                
            else:
                # 下单失败，记录失败信息
                log.warning(f"[{strategy_id}] safe_order: {order_message} 失败 - {stock}")
                log.warning(f"  失败原因: {order_message if not order_id else '订单ID为空'}")
                
                # ========== 记录失败交易到全局交易记录 ==========
                if not hasattr(g, 'today_trades'):
                    g.today_trades = []
                
                # 创建失败交易记录
                failed_trade_record = {
                    'stock': stock,
                    'action': action,  # '买入' 或 '卖出'
                    'order_id': None,
                    'order_type': order_type,
                    'amount': 0,  # 失败时成交数量为0
                    'price': 0.0,
                    'value': 0.0,
                    'strategy_id': strategy_id,
                    'timestamp': transform_date(context.current_dt, 'str_yyyy_mm_dd_hh_mm_ss'),
                    'message': f'{order_message} 失败',
                    'reason': f'{order_message} 失败 - {order_message if not order_id else "订单ID为空"}',  # 添加reason字段
                    'status': 'failed',  # 标记为失败状态
                    'failure_reason': order_message if not order_id else '订单ID为空'
                }
                
                # 添加到全局交易记录
                g.today_trades.append(failed_trade_record)
                log.debug(f"[{strategy_id}] safe_order: 失败交易记录已添加到 g.today_trades")
            
            # ========== 步骤7：更新策略标签系统 ==========
            # 只有在下单成功时才更新标签系统
            if order_id is not None:
                try:
                    # 确保全局变量存在
                    if not hasattr(g, 'strategy_tags'):
                        g.strategy_tags = {}
                    if not hasattr(g, 'strategy_positions'):
                        g.strategy_positions = {}

                    if is_buy:
                        # ========== 买入成功时 ==========
                        # 设置策略标签
                        g.strategy_tags[stock] = strategy_id
                        log.info(f"[{strategy_id}] safe_order: 设置策略标签: {stock} -> {strategy_id}")

                        # 更新策略持仓列表
                        if strategy_id not in g.strategy_positions:
                            g.strategy_positions[strategy_id] = []
                        if stock not in g.strategy_positions[strategy_id]:
                            g.strategy_positions[strategy_id].append(stock)
                            log.info(f"[{strategy_id}] safe_order: 更新持仓列表: {stock} 已添加到 {strategy_id}")

                    else:
                        # ========== 卖出成功时 ==========
                        # 删除策略标签
                        if stock in g.strategy_tags:
                            del g.strategy_tags[stock]
                            log.info(f"[{strategy_id}] safe_order: 删除策略标签: {stock}")

                        # 更新策略持仓列表
                        if strategy_id in g.strategy_positions and stock in g.strategy_positions[strategy_id]:
                            g.strategy_positions[strategy_id].remove(stock)
                            log.info(f"[{strategy_id}] safe_order: 更新持仓列表: {stock} 已从 {strategy_id} 移除")

                except Exception as e:
                    log.error(f"[{strategy_id}] safe_order: 更新策略标签系统失败: {str(e)}")
                    # 标签系统更新失败不影响交易结果，只记录日志
            else:
                # 下单失败，不更新标签系统
                log.debug(f"[{strategy_id}] safe_order: 下单失败，跳过策略标签更新")

            # ========== 返回结果 ==========
            return {
                'success': order_id is not None,
                'order_id': order_id,
                'message': order_message
            }
        
        except Exception as e:
            log.error(f"[{strategy_id}] safe_order: 执行失败 - {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            return {
                'success': False,
                'order_id': None,
                'message': f'执行失败: {str(e)}'
            }


# ============================================================================
# 策略基类（BaseStrategy）
# ============================================================================

class BaseStrategy:
    """
    策略基类
    
    功能说明：
    1. 策略标识管理（strategy_id, strategy_name）
    2. 资金池管理（capital_pool）
    3. 持仓标签管理（通过g.strategy_tags和g.strategy_positions）
    4. 买卖日志记录（通过g.today_trades）
    5. 策略配置（params）
    
    设计原则：
    - 所有策略类都应该继承自BaseStrategy
    - 提供统一的初始化接口
    - 提供统一的盘前、盘中、盘后处理接口
    - 便于后续策略移植和扩展
    
    使用方法：
    - 继承BaseStrategy类
    - 重写before_trading_start、execute_trade、after_trading_end方法
    - 在__init__中调用父类初始化方法
    """
    
    def __init__(self, strategy_id, strategy_name, params=None):
        """
        策略基类初始化函数
        
        参数:
            strategy_id: 策略唯一标识符（如 'limit_up', 'swing'）
            strategy_name: 策略名称（如 '五合一打板策略', '小市值波段策略'）
            params: 策略参数字典（可选，默认为None）
        
        初始化内容：
        - 策略标识（strategy_id, strategy_name）
        - 策略参数（params）
        - 资金池（capital_pool，初始为0）
        - 持仓列表（positions，初始为空列表）
        - 交易统计（trade_stats）
        """
        # ========== 策略标识 ==========
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        
        # ========== 策略参数 ==========
        self.params = params if params is not None else {}
        
        # ========== 资金池管理 ==========
        self.capital_pool = 0.0  # 策略资金池金额（初始为0，由StrategyManager分配）
        
        # ========== 持仓管理 ==========
        self.positions = []  # 策略持仓股票代码列表
        
        # ========== 交易统计 ==========
        self.trade_stats = {
            'total_trades': 0,  # 总交易次数
            'buy_trades': 0,    # 买入次数
            'sell_trades': 0,   # 卖出次数
            'total_profit': 0.0,  # 总盈亏
            'win_rate': 0.0,    # 胜率
        }
        
        # ========== 策略状态 ==========
        self.enabled = True  # 策略启用状态（默认启用）
        
        log.info(f"[{self.strategy_id}] 策略基类初始化完成")
        log.info(f"  策略名称: {self.strategy_name}")
        log.info(f"  策略参数: {self.params}")
    
    def before_trading_start(self, context):
        """
        策略盘前准备函数（基类方法，子类可重写）
        
        功能说明：
        - 清空当日变量
        - 检查策略状态
        - 更新策略持仓列表
        - 获取资金池信息
        - 记录盘前统计信息
        
        参数:
            context: 聚宽上下文对象
        
        注意：
        - 基类方法提供通用框架
        - 子类应该在重写后调用 super().before_trading_start(context) 保留基础逻辑
        - 子类可以在此基础上添加特定的盘前准备逻辑
        """
        try:
            # ========== 步骤1：检查策略是否启用 ==========
            if not self.enabled:
                return
            
            log.info(f"[{self.strategy_id}] 策略盘前准备开始")
            
            # ========== 步骤2：清空当日交易记录 ==========
            if hasattr(g, 'today_trades'):
                # 不清空g.today_trades，这是全局变量
                pass
            
            # 初始化策略当日交易标记
            self._today_bought = False  # 今日是否已买入
            self._today_sold = False   # 今日是否已卖出
            
            # ========== 步骤3：更新策略持仓列表 ==========
            self._update_strategy_positions(context)
            
            # ========== 步骤4：获取策略资金池信息 ==========
            self._update_capital_pool(context)
            
            # ========== 步骤5：记录盘前统计信息 ==========
            self._record_pre_market_stats(context)
            
            log.info(f"[{self.strategy_id}] 策略盘前准备完成")
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 盘前准备失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
    
    def _update_strategy_positions(self, context):
        """
        更新策略持仓列表（内部方法）
        
        功能：
        - 从g.strategy_tags中获取属于当前策略的持仓股票
        - 更新self.positions列表
        """
        try:
            # 从全局变量g中获取属于当前策略的持仓股票
            if hasattr(g, 'strategy_tags'):
                self.positions = [
                    stock for stock, strategy_id in g.strategy_tags.items() 
                    if strategy_id == self.strategy_id
                ]
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 更新持仓列表失败: {str(e)}")
            self.positions = []
    
    def _update_capital_pool(self, context):
        """
        更新策略资金池信息（内部方法）
        
        功能：
        - 从StrategyManager获取策略资金池金额
        - 更新self.capital_pool属性
        """
        try:
            # 从StrategyManager获取策略资金池金额
            if hasattr(g, 'strategy_manager') and hasattr(g.strategy_manager, 'capital_pools'):
                pool = g.strategy_manager.capital_pools.get(self.strategy_id, {})
                self.capital_pool = pool.get('amount', 0)
                
        except Exception as e:
            log.error(f"[{self.strategy_id}] 更新资金池信息失败: {str(e)}")
            self.capital_pool = 0.0
    
    def _record_pre_market_stats(self, context):
        """
        记录盘前统计信息（内部方法）
        
        功能：
        - 记录账户总览信息
        - 记录策略持仓情况
        """
        try:
            # 记录账户总览
            total_value = context.portfolio.total_value
            cash = context.portfolio.cash
            position_value = total_value - cash
            
            log.info(f"[{self.strategy_id}] 账户总览:")
            log.info(f"  总市值: {total_value:.2f}元")
            log.info(f"  现金: {cash:.2f}元 ({cash/total_value*100:.1f}%)")
            log.info(f"  持仓: {position_value:.2f}元 ({position_value/total_value*100:.1f}%)")
            log.info(f"  资金池: {self.capital_pool:.2f}元")
            log.info(f"  持仓数: {len(self.positions)}")
            
            # 记录策略持仓明细
            if self.positions:
                log.info(f"[{self.strategy_id}] 持仓明细:")
                current_data = get_current_data()
                for stock in self.positions:
                    try:
                        position = context.portfolio.positions.get(stock)
                        if position and position.total_amount > 0:
                            # 不显示股票名称，避免未来函数问题
                            # 说明：get_security_info会返回当前时间点的信息，
                            #      如果股票后来变成了ST，会导致显示不准确
                            market_value = position.total_amount * position.price
                            log.info(f"  {stock}: {position.total_amount:.0f}股, 市值{market_value:.2f}元")
                    except Exception as e:
                        log.warning(f"  {stock}: 获取持仓信息失败 - {str(e)}")
        
        except Exception as e:
            log.error(f"[{self.strategy_id}] 记录盘前统计信息失败: {str(e)}")
    
    def execute_trade(self, context):
        """
        执行买卖逻辑（基类方法，子类可重写）
        
        功能说明：
        - 检查交易时段和策略状态
        - 获取策略资金池
        - 执行买入逻辑
        - 执行卖出逻辑
        - 记录交易后状态
        
        参数:
            context: 聚宽上下文对象
        
        注意：
        - 基类方法提供通用框架
        - 子类应该重写此方法以实现具体逻辑
        - 子类可以调用 super().execute_trade(context) 保留基础逻辑
        """
        try:
            # ========== 步骤1：检查策略是否启用 ==========
            if not self.enabled:
                return
            
            # ========== 步骤2：检查当前交易时段 ==========
            time_status = get_trading_time_status(context)
            if time_status not in ['morning', 'afternoon']:
                return
            
            log.info(f"[{self.strategy_id}] 执行交易逻辑开始")
            
            # ========== 步骤3：交易前准备 ==========
            self._prepare_for_trade(context)
            
            # ========== 步骤4：执行卖出逻辑（先卖后买，释放资金） ==========
            self._execute_sell_logic(context)
            
            # ========== 步骤5：执行买入逻辑 ==========
            self._execute_buy_logic(context)
            
            # ========== 步骤6：交易后处理 ==========
            self._after_trade(context)
            
            log.info(f"[{self.strategy_id}] 执行交易逻辑完成")
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 交易逻辑执行失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
    
    def _prepare_for_trade(self, context):
        """
        交易前准备（内部方法）
        
        功能：
        - 更新策略资金池
        - 更新策略持仓列表
        - 检查资金池是否充足
        """
        try:
            # 更新策略资金池
            self._update_capital_pool(context)
            
            # 更新策略持仓列表
            self._update_strategy_positions(context)
            
            # 检查资金池是否充足
            if self.capital_pool <= 0:
                log.warning(f"[{self.strategy_id}] 资金池为0，无法进行交易")            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 交易前准备失败: {str(e)}")
    
    def _execute_sell_logic(self, context):
        """
        执行卖出逻辑（内部方法，子类可重写）
        
        功能：
        - 检查持仓股票
        - 判断是否需要卖出
        - 执行卖出操作
        
        注意：
        - 基类方法仅提供框架
        - 子类应该重写此方法实现具体卖出逻辑
        """
        try:
            log.debug(f"[{self.strategy_id}] 执行卖出逻辑（基类方法）")
            
            # 子类可以在此处添加具体的卖出逻辑
            # 示例：检查持仓股票，根据策略条件判断是否卖出
            
            # 更新当日卖出标记
            self._today_sold = False
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 卖出逻辑执行失败: {str(e)}")
    
    def _execute_buy_logic(self, context):
        """
        执行买入逻辑（内部方法，子类可重写）
        
        功能：
        - 检查可用资金
        - 筛选买入标的
        - 执行买入操作
        
        注意：
        - 基类方法仅提供框架
        - 子类应该重写此方法实现具体买入逻辑
        """
        try:
            log.debug(f"[{self.strategy_id}] 执行买入逻辑（基类方法）")
            
            # 子类可以在此处添加具体的买入逻辑
            # 示例：检查资金池，筛选股票，执行买入操作
            
            # 更新当日买入标记
            self._today_bought = False
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 买入逻辑执行失败: {str(e)}")
    
    def _after_trade(self, context):
        """
        交易后处理（内部方法）
        
        功能：
        - 更新交易统计
        - 记录交易后状态
        """
        try:
            # 更新策略持仓列表
            self._update_strategy_positions(context)
            
            # 更新策略资金池
            self._update_capital_pool(context)
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 交易后处理失败: {str(e)}")
    
    def after_trading_end(self, context):
        """
        策略盘后处理函数（基类方法，子类可重写）
        
        功能说明：
        - 统计当日交易
        - 更新策略绩效
        - 清理临时数据
        
        参数:
            context: 聚宽上下文对象
        
        注意：
        - 基类方法提供通用框架
        - 子类应该重写此方法以实现具体逻辑
        - 子类可以调用 super().after_trading_end(context) 保留基础逻辑
        """
        try:
            # ========== 步骤1：检查策略是否启用 ==========
            if not self.enabled:
                return
            
            log.info(f"[{self.strategy_id}] 盘后处理开始")
            
            # ========== 步骤2：统计当日交易 ==========
            self._record_daily_trades(context)
            
            # ========== 步骤3：更新策略绩效 ==========
            self._update_strategy_performance(context)
            
            # ========== 步骤4：清理当日临时标记 ==========
            self._cleanup_daily_temp()
            
            # ========== 步骤5：记录策略绩效和持仓信息 ==========
            self._record_strategy_stats(context)
            
            log.info(f"[{self.strategy_id}] 盘后处理完成")
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 盘后处理失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
    
    def _record_daily_trades(self, context):
        """
        统计当日交易（内部方法）
        
        功能：
        - 从g.today_trades中筛选当前策略的交易
        - 统计买入/卖出次数
        - 计算当日盈亏
        """
        try:
            # 获取当前策略的当日交易记录
            if not hasattr(g, 'today_trades'):
                return
            
            # 过滤掉None值（交易失败的记录）
            valid_trades = [trade for trade in g.today_trades 
                          if trade is not None and trade.get('strategy_id') == self.strategy_id]
            
            if not valid_trades:
                return
            
            # 统计交易情况
            buy_trades = [t for t in valid_trades if t.get('action') == '买入']
            sell_trades = [t for t in valid_trades if t.get('action') == '卖出']
            
            log.info(f"[{self.strategy_id}] 当日交易统计:")
            log.info(f"  总交易数: {len(valid_trades)}")
            log.info(f"  买入次数: {len(buy_trades)}")
            log.info(f"  卖出次数: {len(sell_trades)}")
            
            # 计算当日盈亏（基于卖出交易）
            if sell_trades:
                total_profit = sum(t.get('profit', 0) for t in sell_trades)
                avg_profit_pct = sum(t.get('profit_pct', 0) for t in sell_trades) / len(sell_trades)
                
                # 统计盈利和亏损交易
                profit_trades = [t for t in sell_trades if t.get('profit', 0) > 0]
                loss_trades = [t for t in sell_trades if t.get('profit', 0) <= 0]
                win_rate = len(profit_trades) / len(sell_trades) if sell_trades else 0
                
                log.info(f"  当日盈亏: {total_profit:+.2f}元")
                log.info(f"  平均盈亏: {avg_profit_pct:+.2%}")
                log.info(f"  盈利交易: {len(profit_trades)}, 亏损交易: {len(loss_trades)}, 胜率: {win_rate:.2%}")
            
            # 详细交易记录
            if len(valid_trades) <= 10:  # 交易数量不超过10时输出详细记录
                log.info(f"[{self.strategy_id}] 交易明细:")
                for trade in valid_trades:
                    stock_code = trade.get('stock', '')
                    action = trade['action']
                    price = trade.get('price', 0)
                    amount = trade.get('amount', 0)
                    
                    if action == '卖出':
                        profit = trade.get('profit', 0)
                        profit_pct = trade.get('profit_pct', 0)
                        log.info(f"  {stock_code} - {action} - 价格:{price:.2f} - 数量:{amount:.0f} - 盈亏:{profit:+.2f}元 ({profit_pct:+.2f}%)")
                    else:
                        log.info(f"  {stock_code} - {action} - 价格:{price:.2f} - 数量:{amount:.0f}")
        
        except Exception as e:
            log.error(f"[{self.strategy_id}] 统计当日交易失败: {str(e)}")
    
    def _update_strategy_performance(self, context):
        """
        更新策略绩效（内部方法）
        
        功能：
        - 更新总交易次数、买入/卖出次数
        - 更新总盈亏
        - 更新胜率
        """
        try:
            # 获取当前策略的当日交易记录
            if not hasattr(g, 'today_trades'):
                return
            
            # 过滤掉None值（交易失败的记录）
            valid_trades = [trade for trade in g.today_trades 
                          if trade is not None and trade.get('strategy_id') == self.strategy_id]
            
            if not valid_trades:
                return
            
            # 统计交易次数
            buy_count = len([t for t in valid_trades if t.get('action') == '买入'])
            sell_count = len([t for t in valid_trades if t.get('action') == '卖出'])
            
            # 更新交易统计
            self.trade_stats['total_trades'] += len(valid_trades)
            self.trade_stats['buy_trades'] += buy_count
            self.trade_stats['sell_trades'] += sell_count
            
            # 更新总盈亏（基于卖出交易）
            sell_trades = [t for t in valid_trades if t.get('action') == '卖出']
            if sell_trades:
                total_profit = sum(t.get('profit', 0) for t in sell_trades)
                self.trade_stats['total_profit'] += total_profit
            
            # 更新胜率（基于所有卖出交易）
            all_sell_trades = []
            if hasattr(g, 'trade_stats') and 'trade_details' in g.trade_stats:
                all_sell_trades = [t for t in g.trade_stats['trade_details'] 
                                 if t is not None and t.get('strategy_id') == self.strategy_id 
                                 and t.get('action') == '卖出']
            
            if all_sell_trades:
                profit_trades = [t for t in all_sell_trades if t.get('profit', 0) > 0]
                self.trade_stats['win_rate'] = len(profit_trades) / len(all_sell_trades)
            
            log.debug(f"[{self.strategy_id}] 策略绩效已更新:")
            log.debug(f"  总交易: {self.trade_stats['total_trades']}次")
            log.debug(f"  买入: {self.trade_stats['buy_trades']}次, 卖出: {self.trade_stats['sell_trades']}次")
            log.debug(f"  总盈亏: {self.trade_stats['total_profit']:+.2f}元")
            log.debug(f"  胜率: {self.trade_stats['win_rate']:.2%}")
        
        except Exception as e:
            log.error(f"[{self.strategy_id}] 更新策略绩效失败: {str(e)}")
    
    def _cleanup_daily_temp(self):
        """
        清理当日临时标记（内部方法）
        
        功能：
        - 清理当日买入/卖出标记
        """
        try:
            # 清理当日交易标记
            if hasattr(self, '_today_sold'):
                self._today_sold = False
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 清理当日临时标记失败: {str(e)}")
    
    def _record_strategy_stats(self, context):
        """
        记录策略绩效和持仓信息（内部方法）
        
        功能：
        - 记录账户总览
        - 记录策略持仓情况
        - 记录策略绩效
        """
        try:
            # 记录账户总览
            total_value = context.portfolio.total_value
            cash = context.portfolio.cash
            position_value = total_value - cash
            
            log.info(f"[{self.strategy_id}] 账户总览:")
            log.info(f"  总市值: {total_value:.2f}元")
            log.info(f"  现金: {cash:.2f}元 ({cash/total_value*100:.1f}%)")
            log.info(f"  持仓: {position_value:.2f}元 ({position_value/total_value*100:.1f}%)")
            log.info(f"  资金池: {self.capital_pool:.2f}元")
            log.info(f"  持仓数: {len(self.positions)}")
            
            # 记录策略持仓明细
            if self.positions:
                log.info(f"[{self.strategy_id}] 持仓明细:")
                current_data = get_current_data()
                for stock in self.positions:
                    try:
                        position = context.portfolio.positions.get(stock)
                        if position and position.total_amount > 0:
                            # 不显示股票名称，避免未来函数问题
                            # 说明：get_security_info会返回当前时间点的信息，
                            #      如果股票后来变成了ST，会导致显示不准确
                            market_value = position.total_amount * position.price
                            profit = market_value - (position.avg_cost * position.total_amount)
                            profit_pct = (profit / (position.avg_cost * position.total_amount) * 100) if position.total_amount > 0 else 0
                            log.info(f"  {stock}: {position.total_amount:.0f}股, 市值{market_value:.2f}元, 盈亏:{profit:+.2f}元 ({profit_pct:+.2f}%)")
                    except Exception as e:
                        log.warning(f"  {stock}: 获取持仓信息失败 - {str(e)}")
            
            # 记录策略绩效
            if self.trade_stats['total_trades'] > 0:
                log.info(f"[{self.strategy_id}] 策略绩效:")
                log.info(f"  总交易: {self.trade_stats['total_trades']}次")
                log.info(f"  买入: {self.trade_stats['buy_trades']}次, 卖出: {self.trade_stats['sell_trades']}次")
                log.info(f"  总盈亏: {self.trade_stats['total_profit']:+.2f}元")
                log.info(f"  胜率: {self.trade_stats['win_rate']:.2%}")
        
        except Exception as e:
            log.error(f"[{self.strategy_id}] 记录策略绩效和持仓信息失败: {str(e)}")
    
    def get_capital_pool(self):
        """
        获取策略资金池金额
        
        返回:
            float: 策略资金池金额
        """
        # 从全局变量g中获取最新的资金池金额
        if hasattr(g, 'strategy_manager') and hasattr(g.strategy_manager, 'capital_pools'):
            pool = g.strategy_manager.capital_pools.get(self.strategy_id, {})
            pool_amount = pool.get('amount', 0)
            self.capital_pool = pool_amount
            return pool_amount
        else:
            return self.capital_pool
    
    def check_capital_sufficient(self, required_amount):
        """
        检查资金池是否充足
        
        功能：
        - 检查资金池是否足够支付指定金额
        - 返回检查结果和详细信息
        
        参数:
            required_amount: 需要的金额
        
        返回:
            dict: {
                'sufficient': bool,  # 是否充足
                'available': float,   # 可用金额
                'required': float,    # 需要金额
                'shortage': float,   # 缺口金额
                'usage_ratio': float # 使用率
            }
        """
        try:
            # 更新资金池信息
            current_capital = self.get_capital_pool()
            
            # 计算缺口
            shortage = max(0, required_amount - current_capital)
            
            # 计算使用率（如果有总资金信息）
            usage_ratio = 0.0
            if hasattr(g, 'strategy_manager') and hasattr(g.strategy_manager, 'capital_pools'):
                total_capital = context.portfolio.total_value if hasattr(context, 'portfolio') else 0
                if total_capital > 0:
                    usage_ratio = current_capital / total_capital
            
            # 构建返回结果
            result = {
                'sufficient': current_capital >= required_amount,
                'available': current_capital,
                'required': required_amount,
                'shortage': shortage,
                'usage_ratio': usage_ratio
            }
            
            # 记录日志
            
            return result
        
        except Exception as e:
            log.error(f"[{self.strategy_id}] 检查资金池充足性失败: {str(e)}")
            # 返回最保守的结果（资金不足）
            return {
                'sufficient': False,
                'available': 0.0,
                'required': required_amount,
                'shortage': required_amount,
                'usage_ratio': 0.0
            }
    
    def get_strategy_positions(self):
        """
        获取策略持仓列表
        
        返回:
            list: 策略持仓股票代码列表
        """
        # 从全局变量g中获取最新的持仓列表
        if hasattr(g, 'strategy_positions'):
            return g.strategy_positions.get(self.strategy_id, [])
        else:
            return self.positions
    
    # ============================================================================
    # 阶段三-任务6：持仓标签管理方法
    # ============================================================================
    
    def add_position_tag(self, stock):
        """
        添加持仓标签
        
        功能：
        - 将股票标记为属于当前策略
        - 更新全局变量g.strategy_tags和g.strategy_positions
        
        参数:
            stock: 股票代码（如 '000001.XSHE'）
        
        返回:
            bool: 是否添加成功
        """
        try:
            # 确保全局变量存在
            if not hasattr(g, 'strategy_tags'):
                g.strategy_tags = {}
            if not hasattr(g, 'strategy_positions'):
                g.strategy_positions = {}
            
            # 检查股票是否已被其他策略持有
            if stock in g.strategy_tags:
                owner_strategy = g.strategy_tags[stock]
                if owner_strategy != self.strategy_id:
                    log.warning(f"[{self.strategy_id}] 股票 {stock} 已被策略 {owner_strategy} 持有，无法添加标签")
                    return False
                else:
                    # 同一策略持有该股票，跳过
                    return True
            
            # 添加策略标签
            g.strategy_tags[stock] = self.strategy_id
            
            # 更新策略持仓列表
            
            return True
        
        except Exception as e:
            log.error(f"[{self.strategy_id}] 添加持仓标签失败: {str(e)}")
            return False
    
    def remove_position_tag(self, stock):
        """
        删除持仓标签
        
        功能：
        - 从当前策略中移除股票标签
        - 更新全局变量g.strategy_tags和g.strategy_positions
        
        参数:
            stock: 股票代码（如 '000001.XSHE'）
        
        返回:
            bool: 是否删除成功
        """
        try:
            # 确保全局变量存在
            if not hasattr(g, 'strategy_tags'):
                g.strategy_tags = {}
            if not hasattr(g, 'strategy_positions'):
                g.strategy_positions = {}
            
            # 检查股票是否属于当前策略
            if stock in g.strategy_tags:
                owner_strategy = g.strategy_tags[stock]
                if owner_strategy != self.strategy_id:
                    log.warning(f"[{self.strategy_id}] 股票 {stock} 属于策略 {owner_strategy}，无法删除标签")
                    return False
            
            # 删除策略标签
            if stock in g.strategy_tags:
                del g.strategy_tags[stock]
                log.debug(f"[{self.strategy_id}] 删除持仓标签: {stock}")
            
            # 更新策略持仓列表
            if self.strategy_id in g.strategy_positions and stock in g.strategy_positions[self.strategy_id]:
                g.strategy_positions[self.strategy_id].remove(stock)
                log.debug(f"[{self.strategy_id}] 更新持仓列表: {stock} 已从 {self.strategy_id} 移除")
            
            return True
        
        except Exception as e:
            log.error(f"[{self.strategy_id}] 删除持仓标签失败: {str(e)}")
            return False
    
    def get_position_tag(self, stock):
        """
        获取股票所属策略
        
        参数:
            stock: 股票代码（如 '000001.XSHE'）
        
        返回:
            str: 策略ID，如果股票无标签则返回None
        """
        try:
            if hasattr(g, 'strategy_tags') and stock in g.strategy_tags:
                return g.strategy_tags[stock]
            else:
                return None
        except Exception as e:
            log.error(f"[{self.strategy_id}] 获取持仓标签失败: {str(e)}")
            return None
    
    def clear_position_tags(self):
        """
        清空当前策略的所有持仓标签
        
        功能：
        - 删除当前策略持有的所有股票标签
        - 清空g.strategy_tags和g.strategy_positions中属于当前策略的条目
        
        返回:
            bool: 是否清空成功
        """
        try:
            # 确保全局变量存在
            if not hasattr(g, 'strategy_tags'):
                g.strategy_tags = {}
            if not hasattr(g, 'strategy_positions'):
                g.strategy_positions = {}
            
            # 获取当前策略的持仓列表
            current_positions = self.get_strategy_positions()
            
            if not current_positions:
                log.debug(f"[{self.strategy_id}] 当前策略无持仓，无需清空标签")
                return True
            
            # 删除所有持仓标签
            cleared_count = 0
            for stock in current_positions.copy():  # 使用copy避免修改迭代中的列表
                if stock in g.strategy_tags:
                    del g.strategy_tags[stock]
                    cleared_count += 1
                    log.debug(f"[{self.strategy_id}] 删除持仓标签: {stock}")
            
            # 清空策略持仓列表
            g.strategy_positions[self.strategy_id] = []
            
            log.info(f"[{self.strategy_id}] 清空持仓标签完成，共删除 {cleared_count} 个标签")
            return True
        
        except Exception as e:
            log.error(f"[{self.strategy_id}] 清空持仓标签失败: {str(e)}")
            return False


# ============================================================================
# ETF核心资产轮动策略类（继承自BaseStrategy）
# ============================================================================

class ETFRotationStrategy(BaseStrategy):
    """
    ETF核心资产轮动策略类（继承自BaseStrategy）
    
    功能说明：
    - 基于动量因子在4只ETF之间轮动
    - 使用线性加权回归计算动量得分
    - 持仓1只ETF，全仓或空仓
    
    核心逻辑：
    1. ETF池：黄金ETF、纳指100、创业板100、上证180
    2. 动量参考天数：25天
    3. 动量计算：使用线性加权回归计算年化收益率和判定系数的乘积
    4. 安全区间筛选：0 < score ≤ 5
    5. 每日09:30执行交易
    6. 持仓1只ETF，全仓或空仓
    
    原作者：MarioC / wywy1995
    原年化收益：51.11%
    
    实现参考：
    ETF_Core_Asset_Rotation_Strategy.py（原策略原型代码）
    """
    
    def __init__(self, strategy_id='etf_rotation', params=None):
        """
        ETF核心资产轮动策略类初始化函数
        
        参数:
            strategy_id: 策略唯一标识符（默认'etf_rotation'）
            params: 策略参数字典（可选，默认使用默认参数）
        """
        # 调用父类BaseStrategy的__init__方法
        strategy_name = "ETF核心资产轮动策略"
        super().__init__(strategy_id, strategy_name, params)
        
        # ========== 默认策略参数 ==========
        self.params = {
            # ETF池（默认使用4只ETF）
            'etf_pool': [
                '518880.XSHG',  # 黄金ETF（大宗商品）
                '513100.XSHG',  # 纳指100（海外资产）
                '159915.XSHE',  # 创业板100（成长股，科技股，中小盘）
                '510180.XSHG',  # 上证180（价值股，蓝筹股，中大盘）
            ],
            
            # 自动获取ETF池配置
            'auto_fetch_etf_pool': False,  # 是否自动获取ETF池（默认关闭）
            'auto_fetch_num': 10,  # 自动获取时目标ETF数量
            'auto_fetch_min_days': 480,  # 自动获取时最小上市天数（480天，约2年，平衡流动性和历史数据）
            
            # 动量参数
            'm_days': 25,          # 动量参考天数
            'target_num': 1,       # 目标持仓数量
            
            # 安全区间
            'min_score': 0,        # 最小动量得分
            'max_score': 5,        # 最大动量得分
        }
        
        # 如果提供了自定义参数，更新默认参数
        if params is not None:
            self.params.update(params)
        
        # ========== 策略状态变量 ==========
        self.last_rank_list = []  # 上次排名列表（用于日志对比）
        
        # 当日交易标记
        self.buy_executed = False  # 今日买入是否已执行
        self.sell_executed = False  # 今日卖出是否已执行
        
        log.info(f"[{self.strategy_id}] ETF核心资产轮动策略初始化完成")
        if self.params['auto_fetch_etf_pool']:
            log.info(f"  ETF池: 自动获取（目标数量: {self.params['auto_fetch_num']}只）")
        else:
            log.info(f"  ETF池: {self.params['etf_pool']}")
        log.info(f"  动量参考天数: {self.params['m_days']}天")
        log.info(f"  目标持仓数量: {self.params['target_num']}只")
        log.info(f"  安全区间: {self.params['min_score']} < score ≤ {self.params['max_score']}")
    
    def before_trading_start(self, context):
        """
        策略盘前准备函数
        
        功能：
        - 调用父类BaseStrategy的盘前准备
        - 清空当日交易标记
        - 更新策略持仓列表
        - 自动获取ETF池（如果开启）
        """
        try:
            # 调用父类BaseStrategy的盘前准备
            super().before_trading_start(context)
            
            # 清空当日交易标记
            self.buy_executed = False
            self.sell_executed = False
            
            log.info(f"[{self.strategy_id}] ETF轮动策略盘前准备完成")
            log.info(f"  当前ETF池数量: {len(self.params['etf_pool'])} 只")
            log.info(f"  当前ETF池: {self.params['etf_pool']}")
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 盘前准备失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
    
    def execute_trade(self, context):
        """
        策略交易执行函数
        
        功能：
        - 计算动量因子
        - 获取ETF排名
        - 执行买卖操作
        
        参数:
            context: 聚宽上下文对象
        """
        try:
            log.info(f"\n{'='*60}")
            log.info(f"[{self.strategy_id}] ETF轮动策略交易执行开始")
            log.info(f"{'='*60}")
            
            # 步骤1：计算动量因子并获取ETF排名
            rank_list = self.get_rank(context)
            
            # 步骤2：执行买卖操作
            self.trade(context, rank_list)
            
            log.info(f"{'='*60}")
            log.info(f"[{self.strategy_id}] ETF轮动策略交易执行完成")
            log.info(f"{'='*60}\n")
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 交易执行失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
    
    def MOM(self, etf: str, context: Any) -> float:
        """
        计算动量因子（MOM）
        
        使用线性加权回归计算年化收益率和判定系数的乘积
        
        参数:
            etf: ETF代码
            context: 聚宽上下文对象
        
        返回:
            score: 动量得分（年化收益率 × 判定系数）
        """
        try:
            import math
            
            # 获取历史收盘价数据
            df = attribute_history(etf, self.params['m_days'], '1d', ['close'])
            
            # 对收盘价取对数
            y = np.log(df['close'].values)
            n = len(y)
            
            # x轴：0, 1, 2, ..., n-1
            x = np.arange(n)
            
            # 线性增加权重（从1到2）
            weights = np.linspace(1, 2, n)
            
            # 线性加权回归
            slope, intercept = np.polyfit(x, y, 1, w=weights)
            
            # 计算年化收益率
            annualized_returns = math.pow(math.exp(slope), 250) - 1
            
            # 计算判定系数R²
            residuals = y - (slope * x + intercept)
            weighted_residuals = weights * residuals**2
            r_squared = 1 - (np.sum(weighted_residuals) / np.sum(weights * (y - np.mean(y))**2))
            
            # 动量得分 = 年化收益率 × 判定系数
            score = annualized_returns * r_squared
            
            return score
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 计算{etf}动量因子失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            return 0.0
    
    def get_rank(self, context: Any) -> List[str]:
        """
        获取ETF排名
        
        功能：
        - 计算所有ETF的动量得分
        - 按得分排序
        - 筛选安全区间内的ETF
        
        参数:
            context: 聚宽上下文对象
        
        返回:
            rank_list: 排序后的ETF列表（按得分从高到低）
        """
        try:
            etf_pool = self.params['etf_pool']
            score_list = []
            
            # 计算每个ETF的动量得分
            for etf in etf_pool:
                score = self.MOM(etf, context)
                score_list.append(score)
            
            # 创建DataFrame并排序
            df = pd.DataFrame(index=etf_pool, data={'score': score_list})
            df = df.sort_values(by='score', ascending=False)
            
            # 安全区间筛选：0 < score ≤ 5
            df_filtered = df[(df['score'] > self.params['min_score']) & (df['score'] <= self.params['max_score'])]
            
            # 获取排名列表
            rank_list = list(df_filtered.index)
            
            # 如果没有符合条件的ETF，返回空列表（空仓）
            if len(rank_list) == 0:
                log.info(f"[{self.strategy_id}] 所有ETF得分不在安全区间，空仓")
            else:
                log.info(f"[{self.strategy_id}] ETF排名: {rank_list}")
            
            return rank_list
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 获取ETF排名失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            return []
    
    def trade(self, context, rank_list):
        """
        执行交易操作
        
        功能：
        - 卖出不在目标列表中的ETF
        - 买入目标列表中的ETF
        
        参数:
            context: 聚宽上下文对象
            rank_list: 排序后的ETF列表（按得分从高到低）
        """
        try:
            # ========== 资金流动日志：交易前状态 ==========
            total_value = context.portfolio.total_value
            available_cash = context.portfolio.available_cash
            position_value = total_value - available_cash
            log.info(f"【资金流动】{self.strategy_id} 交易前状态:")
            log.info(f"  总资产: {total_value:.2f}元, 可用资金: {available_cash:.2f}元, 持仓市值: {position_value:.2f}元")
            log.info(f"  策略资金池: {self.capital_pool:.2f}元")
            log.info(f"  当前持仓数: {len(context.portfolio.positions)}只")
            
            target_num = self.params['target_num']
            target_list = rank_list[:target_num]
            
            log.info(f"【资金流动】目标持仓: {target_list}")
            
            # ========== 步骤1：卖出 ==========
            hold_list = list(context.portfolio.positions.keys())
            total_sell_value = 0
            
            for etf in hold_list:
                # 策略标签检查：只卖出属于当前策略的持仓
                if hasattr(g, 'strategy_tags') and etf in g.strategy_tags:
                    stock_strategy_id = g.strategy_tags[etf]
                    if stock_strategy_id != self.strategy_id:
                        continue
                
                # 如果ETF不在目标列表中，卖出
                if etf not in target_list:
                    try:
                        position = context.portfolio.positions[etf]
                        position_value_before = position.total_amount
                        log.info(f"【资金流动】准备卖出 {etf}: 持仓市值 {position_value_before:.2f}元")
                        
                        order_target_value(etf, 0)
                        total_sell_value += position_value_before
                        log.info(f"【资金流动】已卖出: {etf}, 预计释放资金 {position_value_before:.2f}元")
                        
                        # 记录交易
                        self._record_trade(context, etf, 0, '卖出', '不在目标列表中')
                        
                        # 删除策略标签
                        if hasattr(g, 'strategy_tags') and etf in g.strategy_tags:
                            del g.strategy_tags[etf]
                        
                    except Exception as e:
                        log.error(f"[{self.strategy_id}] 卖出{etf}失败: {str(e)}")
            
            if total_sell_value > 0:
                log.info(f"【资金流动】卖出阶段完成，合计释放资金: {total_sell_value:.2f}元")
            
            # ========== 步骤2：买入 ==========
            # 获取当前策略的持仓（只统计属于当前策略的ETF）
            strategy_hold_list = []
            for etf in hold_list:
                if hasattr(g, 'strategy_tags') and etf in g.strategy_tags:
                    if g.strategy_tags[etf] == self.strategy_id:
                        strategy_hold_list.append(etf)
            
            hold_list = strategy_hold_list  # 更新为只包含当前策略的持仓
            
            if len(hold_list) < target_num:
                # 计算每只ETF的买入金额（使用策略自己的资金池）
                value = self.capital_pool / (target_num - len(hold_list))
                log.info(f"【资金流动】买入阶段: 每只目标ETF买入金额 {value:.2f}元")
                
                for etf in target_list:
                    # 检查是否已经持有
                    if etf in hold_list:
                        log.info(f"【资金流动】跳过买入 {etf}: 已在持仓中")
                        continue
                    
                    try:
                        # 检查是否有策略标签冲突
                        if hasattr(g, 'strategy_tags') and etf in g.strategy_tags:
                            owner = g.strategy_tags[etf]
                            log.warning(f"[{self.strategy_id}] 跳过买入: {etf} (已被策略{owner}持有)")
                            continue
                        
                        # 检查可用资金是否足够
                        current_available = context.portfolio.available_cash
                        if current_available < value:
                            log.warning(f"【资金流动】可用资金不足: 需要 {value:.2f}元, 当前仅有 {current_available:.2f}元")
                            # 使用可用资金买入
                            value = current_available
                            log.info(f"【资金流动】调整买入金额为可用资金: {value:.2f}元")
                        
                        log.info(f"【资金流动】准备买入 {etf}: 订单金额 {value:.2f}元, 当前可用资金 {current_available:.2f}元")
                        
                        # 执行买入
                        order_target_value(etf, value)
                        log.info(f"【资金流动】已提交买入订单: {etf}")
                        
                        # 记录交易
                        self._record_trade(context, etf, value, '买入', '动量轮动')
                        
                        # 设置策略标签
                        if hasattr(g, 'strategy_tags'):
                            g.strategy_tags[etf] = self.strategy_id
                        
                    except Exception as e:
                        log.error(f"[{self.strategy_id}] 买入{etf}失败: {str(e)}")
            
            # ========== 资金流动日志：交易后状态 ==========
            final_total_value = context.portfolio.total_value
            final_available_cash = context.portfolio.available_cash
            final_position_value = final_total_value - final_available_cash
            log.info(f"【资金流动】{self.strategy_id} 交易后状态:")
            log.info(f"  总资产: {final_total_value:.2f}元, 可用资金: {final_available_cash:.2f}元, 持仓市值: {final_position_value:.2f}元")
            log.info(f"  总资产变化: {final_total_value - total_value:+.2f}元")
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 交易操作失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
    
    def _record_trade(self, context, stock, value, action, reason):
        """
        记录交易日志（内部方法）
        
        参数:
            context: 聚宽上下文对象
            stock: 股票/ETF代码
            value: 交易金额（买入时为正值，卖出时为0）
            action: 交易动作（买入/卖出）
            reason: 交易原因
        """
        try:
            if not hasattr(g, 'today_trades'):
                g.today_trades = []
            
            # 构建交易记录
            trade_record = {
                'stock': stock,
                'action': action,
                'value': value,
                'reason': reason,
                'strategy_id': self.strategy_id,
                'timestamp': context.current_dt.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # 添加到全局交易记录
            g.today_trades.append(trade_record)
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 记录交易日志失败: {str(e)}")

# ============================================================================
# 小市值波段策略类（继承自BaseStrategy）
# ============================================================================

class SwingStrategy(BaseStrategy):
    """小市值波段策略（原作者wellfuture，年化收益57%）"""

    def __init__(self, strategy_id='swing', params=None):
        """初始化策略"""
        strategy_name = "小市值波段策略"
        super().__init__(strategy_id, strategy_name, params)
        
        # 默认参数
        self.params = {
            'index': '399101.XSHE',
            'buy_stock_count': 5,
            'screen_stock_count': 15,
            'down_stock_count': 15,
            'uprate': 8.0,
            'downrate': -3.0,
            'sell_cooldown_days': 5,
            'return_threshold': -0.02,
            'cooldown_days': 5,
            'empty_months': [],
            'money_fund': '511880.XSHG',
        }
        
        if params is not None:
            self.params.update(params)
        
        # 状态变量
        self.stock_list = []
        self.df2 = None
        self.handle_data_flag = False
        self.current_date = None
        self.in_cooldown = False
        self.last_sell_date = None
        self.days_since_sell = 0
        self.sold_stocks_dates = {}
        self.portfolio_values = []
        self.cooldown_count = 0
        self.cooldown_dates = []
        self.today_bought_stocks = set()
        self.today_sold_stocks = set()
        self.buy_executed = False
        self.sell_executed = False
        
        log.info(f"[{self.strategy_id}] 小市值波段策略初始化完成")
        log.info(f"  指数: {self.params['index']}, 持仓: {self.params['buy_stock_count']}只")
        log.info(f"  止盈: {self.params['uprate']}%, 回补: {self.params['downrate']}%")
        log.info(f"  冷静期: {self.params['cooldown_days']}天, 空仓月: {self.params['empty_months']}")
    
    def before_trading_start(self, context):
        """盘前准备：组合监控、空仓月处理、候选池生成、ST检查"""
        try:
            super().before_trading_start(context)
            
            # 组合监控
            self.calculate_portfolio_return(context)
            if self.check_portfolio_decline(context):
                log.info(f"[{self.strategy_id}] 触发冷静期，清仓买入货基")
            
            log.info(f"[{self.strategy_id}] 盘前准备开始")
            
            # 空仓月处理
            if self._is_empty_month(context):
                if self._is_first_trading_day_in_month(context):
                    self._enforce_empty_month_start(context)
                elif self._is_last_trading_day_in_month(context):
                    self._enforce_empty_month_end(context)
            
            # 生成候选池
            self.stock_list = self._get_universe(context)
            self.current_date = self._get_prev_trade_day(context)
            
            # ST双重检查
            log.info(f"[{self.strategy_id}] 候选股票池ST双重检查")
            st_check_stocks = []
            cd = get_current_data()
            
            for s in self.stock_list:
                try:
                    info = cd[s]
                    name = info.name
                    
                    if info.is_st or info.paused:
                        st_check_stocks.append(s)
                        log.warning(f"[{self.strategy_id}] 过滤: {s} - {name}")
                        continue
                    
                    if name and ('ST' in name or '*ST' in name or '退' in name):
                        st_check_stocks.append(s)
                        log.warning(f"[{self.strategy_id}] 过滤: {s} - {name}")
                        continue
                except Exception:
                    continue
            
            if st_check_stocks:
                self.stock_list = [s for s in self.stock_list if s not in st_check_stocks]
                log.info(f"[{self.strategy_id}] 过滤{len(st_check_stocks)}只ST/停牌/退市股票")
            
            # 重置当日标记
            self.today_bought_stocks = set()
            self.today_sold_stocks = set()
            self.buy_executed = False
            self.sell_executed = False
            
            # ========== 步骤4：冷静期天数推进（按交易日计） ==========
            self.days_since_sell = self._trading_days_since_last_sell(context)
            
            # ========== 步骤5：冷静期内即时处理 ==========
            self.check_and_clean_stocks_in_cooldown(context)
            
            # ========== 步骤6：尝试取基本面，按流通市值排序 ==========
            try:
                q = query(valuation.code, valuation.circulating_market_cap, 
                         valuation.market_cap, valuation.pe_ratio, valuation.pe_ratio_lyr) \
                    .filter(valuation.code.in_(self.stock_list))
                df = get_fundamentals(q, self.current_date)
                
                if df is None or df.empty:
                    self.handle_data_flag = False
                    log.warning(f"[{self.strategy_id}] 获取基本面数据失败")
                    return
                
                # 按流通市值从小到大排序
                df = df.sort_values(by='circulating_market_cap', ascending=True) \
                      .sort_values(by='market_cap', ascending=True)
                
                # 仅保留前若干，减少后续计算量
                self.df2 = df.set_index('code')
                self.handle_data_flag = True
                
                log.info(f"[{self.strategy_id}] 基本面数据获取成功，候选池股票数: {len(self.df2)}")
            except Exception as e:
                log.error(f"[{self.strategy_id}] 获取基本面失败: {str(e)}")
                self.handle_data_flag = False
            
            log.info(f"[{self.strategy_id}] 小市值波段策略盘前准备完成")
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 盘前准备失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
    
    def execute_trade(self, context):
        """
        执行买卖逻辑（重写BaseStrategy方法）
        
        功能说明：
        - 检查交易时段和策略状态
        - 根据当前时间执行对应的买卖逻辑
        - 支持定时任务调用（09:31买入，14:49卖出）
        
        参数:
            context: 聚宽上下文对象
        """
        try:
            # 调用父类BaseStrategy的execute_trade方法
            # super().execute_trade(context)  # 不调用父类方法，自定义逻辑
            
            # 检查策略是否启用
            if not self.enabled:
                return
            
            # 检查是否可以处理数据
            if not self.handle_data_flag:
                return
            
            # 检查当前交易时段
            time_status = get_trading_time_status(context)
            if time_status not in ['morning', 'afternoon']:
                return
            
            log.info(f"[{self.strategy_id}] 执行交易逻辑（时段: {time_status}）")
            log.info(f"  冷静期次数更新: {self.cooldown_count}")
            log.info(f"  冷静期状态更新: {self.in_cooldown}")
        except Exception as e:
            log.error(f"[{self.strategy_id}] 交易逻辑执行失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
    
    def after_trading_end(self, context):
        """
        策略盘后处理函数（重写BaseStrategy方法）
        
        功能说明：
        1. 调用父类BaseStrategy的after_trading_end方法
        2. 统计当日交易
        3. 更新策略绩效
        4. 清理临时数据
        
        参数:
            context: 聚宽上下文对象
        """
        try:
            # 调用父类BaseStrategy的after_trading_end方法
            super().after_trading_end(context)
            
            log.info(f"[{self.strategy_id}] 小市值波段策略盘后处理完成")
            
        except Exception as e:
            log.error(f"[{self.strategy_id}] 盘后处理失败: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
    
    # 交易执行方法（兼容调用）
    
    def execute_trade(self, context):
        """仅记录状态，实际买卖通过定时任务执行"""
        try:
            log.info(f"[{self.strategy_id}] SwingStrategy交易执行（仅记录，实际买卖通过定时任务执行）")
            self._update_strategy_positions(context)
            log.info(f"  持仓: {len(self.positions)}只, 资金池: {self.capital_pool:.2f}元, 冷静期: {self.in_cooldown}")
        except Exception as e:
            log.error(f"[{self.strategy_id}] 交易执行记录失败: {str(e)}")
    
    # 工具函数
    
    def _get_prev_trade_day(self, context):
        """获取昨日交易日字符串"""
        ds = get_trade_days(end_date=context.current_dt.date(), count=2)
        return str(ds[-2]) if len(ds) >= 2 else str(context.current_dt.date())
    
    def _get_universe(self, context):
        """获取候选股票池"""
        try:
            pool = get_index_stocks(self.params['index'])
        except Exception:
            pool = []
        return filter_st_paused_stock(pool)
    
    def _is_empty_month(self, context):
        """判断是否是空仓月"""
        try:
            mon = context.current_dt.month
            return hasattr(self, 'params') and hasattr(self.params, 'get') and (mon in self.params.get('empty_months', []))
        except Exception:
            return False
    
    def _is_first_trading_day_in_month(self, context):
        """
        判断是否是每月第一个交易日
        
        参数:
            context: 聚宽上下文对象
        
        返回:
            bool: True表示是每月第一个交易日，False表示不是
        
        实现参考：
        min_cooldown_swing_strategy.py 中的 _is_first_trading_day_in_month 方法
        """
        try:
            cur = context.current_dt.date()
            month_start = cur.replace(day=1)
            days = get_trade_days(start_date=month_start, end_date=cur)
            
            return len(days) == 1 and days[0] == cur
        except Exception as e:
            log.error(f"[{self.strategy_id}] _is_first_trading_day_in_month异常: {str(e)}")
            return False
    
    def _is_last_trading_day_in_month(self, context):
        """
        判断是否是每月最后一个交易日
        
        参数:
            context: 聚宽上下文对象
        
        返回:
            bool: True表示是每月最后一个交易日，False表示不是
        
        实现参考：
        min_cooldown_swing_strategy.py 中的 _is_last_trading_day_in_month 方法
        """
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
    
    def _enforce_empty_month_start(self, context):
        """空仓月开始：清空股票并买入货币基金"""
        try:
            sold_count = 0
            for code, pos in list(context.portfolio.positions.items()):
                if code == self.params['money_fund']:
                    continue
                if code in g.strategy_tags and g.strategy_tags[code] == self.strategy_id:
                    if pos.total_amount > 0:
                        result = g.strategy_manager.safe_order(context, code, 0, self.strategy_id, 'order_target_value')
                        if result['success']:
                            sold_count += 1
            
            if sold_count > 0:
                log.info(f"[{self.strategy_id}] 空仓月开始，卖出{sold_count}只股票")
            
            cash = context.portfolio.cash
            if cash > 0:
                try:
                    cd = get_current_data()
                    price = float(cd[self.params['money_fund']].last_price) if self.params['money_fund'] in cd else 25.0
                    shares = int(cash / price / 100) * 100
                    
                    if shares >= 100:
                        value = shares * price
                        result = g.strategy_manager.safe_order(context, self.params['money_fund'], value, self.strategy_id, 'order_value')
                        if result['success']:
                            log.info(f"[{self.strategy_id}] 买入货币基金: {value:.2f}元")
                    else:
                        log.warning(f"[{self.strategy_id}] 现金不足100股，无法买入货基")
                except Exception as e:
                    result = g.strategy_manager.safe_order(context, self.params['money_fund'], cash, self.strategy_id, 'order_target_value')
                    if result['success']:
                        log.info(f"[{self.strategy_id}] 买入货币基金: {cash:.2f}元")
        except Exception as e:
            log.warning(f"[{self.strategy_id}] 空仓月开始失败: {str(e)}")
    
    def _enforce_empty_month_end(self, context):
        """空仓月结束：卖出货币基金"""
        try:
            if self.params['money_fund'] in context.portfolio.positions:
                pos = context.portfolio.positions[self.params['money_fund']]
                if pos.total_amount > 0:
                    result = g.strategy_manager.safe_order(context, self.params['money_fund'], 0, self.strategy_id, 'order_target_value')
                    if result['success']:
                        log.info(f"[{self.strategy_id}] 卖出货币基金")
                        if hasattr(g, 'strategy_tags') and self.params['money_fund'] in g.strategy_tags:
                            del g.strategy_tags[self.params['money_fund']]
        except Exception as e:
            log.warning(f"[{self.strategy_id}] 空仓月结束失败: {str(e)}")
    
    def _trading_days_since_last_sell(self, context):
        """
        计算距离最后卖出的交易日数
        
        参数:
            context: 聚宽上下文对象
        
        返回:
            int: 交易日数量
        """
        try:
            if not self.last_sell_date:
                return 0
            last = dt.datetime.strptime(self.last_sell_date, '%Y-%m-%d').date()
            start = last + timedelta(days=1)
            days = get_trade_days(start_date=start, end_date=context.current_dt.date())
            return len(days)
        except Exception:
            return 0
    
    def check_and_clean_stocks_in_cooldown(self, context):
        """
        冷静期管理：在冷静期内清空股票并持有货币基金；到期后退出冷静期。
        
        参数:
            context: 聚宽上下文对象
        
        功能：
        - 未开启或未处于冷静期则返回
        - 推进冷静期天数（按交易日计）
        - 到期：卖出货币基金并退出冷静期
        - 冷静期内：清空所有股票（除货基）
        - 用余额买入货币基金（仅加仓，不减仓；满足100股最小交易单位）
        """
        # 未开启或未处于冷静期则返回
        if not self.in_cooldown:
            return
        
        # 推进冷静期天数（按交易日计）
        self.days_since_sell = self._trading_days_since_last_sell(context)
        
        # 到期：卖出货币基金并退出冷静期
        if self.last_sell_date and self.days_since_sell >= self.params['cooldown_days']:
            try:
                if self.params['money_fund'] in context.portfolio.positions:
                    pos = context.portfolio.positions[self.params['money_fund']]
                    amt = getattr(pos, 'total_amount', 0)
                    if amt >= 100:
                        order_target_value(self.params['money_fund'], 0)
                        log.info(f"[{self.strategy_id}] 冷静期结束，卖出货币基金ETF: {self.params['money_fund']}")

                        # 删除货币基金策略标签
                        if hasattr(g, 'strategy_tags') and self.params['money_fund'] in g.strategy_tags:
                            del g.strategy_tags[self.params['money_fund']]
                            log.debug(f"[{self.strategy_id}] 删除货币基金策略标签: {self.params['money_fund']}")
                    else:
                        log.info(f"[{self.strategy_id}] 冷静期结束，但货基持仓不足100股(amt={amt})，暂不卖出")
            except Exception as e:
                log.warning(f"[{self.strategy_id}] 退出冷静期时卖出货基失败: {str(e)}")
            self.in_cooldown = False
            return
        
        # 冷静期内：清空所有股票（除货基）
        for code, pos in list(context.portfolio.positions.items()):
            if code == self.params['money_fund']:
                continue
            try:
                if pos.total_amount > 0:
                    # 检查可平仓数量
                    closeable_amount = getattr(pos, 'closeable_amount', 0)
                    if closeable_amount <= 0:
                        log.warning(f"[{self.strategy_id}] [冷静期清仓] 跳过不可平仓的持仓: {code} (持仓数量: {pos.total_amount:.0f}股, 可平仓数量: {closeable_amount:.0f}股)")
                        continue
                    
                    # 策略标签检查：只卖出属于当前策略的持仓
                    if hasattr(g, 'strategy_tags') and code in g.strategy_tags:
                        stock_strategy_id = g.strategy_tags[code]
                        if stock_strategy_id != self.strategy_id:
                            log.info(f"[{self.strategy_id}] [冷静期清仓] 跳过其他策略的持仓: {code} (策略: {stock_strategy_id})")
                            continue
                    else:
                        # 如果没有策略标签，也跳过（可能是历史遗留持仓或其他策略的持仓）
                        log.info(f"[{self.strategy_id}] [冷静期清仓] 跳过无策略标签的持仓: {code}")
                        continue
                    
                    order_target_value(code, 0)
                    log.info(f"[{self.strategy_id}] 冷静期内卖出股票: {code}")
            except Exception as e:
                log.warning(f"[{self.strategy_id}] 冷静期内清仓失败 {code}: {str(e)}")
        
        # 用余额买入货币基金（仅加仓，不减仓；满足100股最小交易单位）
        try:
            cd = get_current_data()
            price = float(cd[self.params['money_fund']].last_price) if self.params['money_fund'] in cd else None
            if price is None or price <= 0:
                # 兜底用昨收
                ybar = get_price(self.params['money_fund'], end_date=self._get_prev_trade_day(context),
                                count=1, frequency='daily', fields=['close'])
                if ybar is not None and not ybar.empty:
                    price = float(ybar['close'].iloc[-1])
            if price and price > 0:
                cash = context.portfolio.cash
                pos = context.portfolio.positions.get(self.params['money_fund'], None)
                cur_amt = getattr(pos, 'total_amount', 0) if pos else 0
                cur_val = cur_amt * price
                # 仅当现金可买入至少100股时才加仓
                lot_cash = price * 100
                if cash >= lot_cash:
                    target_val = cur_val + cash
                    order_target_value(self.params['money_fund'], target_val)
                    log.info(f"[{self.strategy_id}] 冷静期持有货币基金ETF: {self.params['money_fund']} 金额: {target_val:.2f}")

                    # 设置策略标签（重要：确保货币基金被正确标记为当前策略的持仓）
                    if hasattr(g, 'strategy_tags'):
                        g.strategy_tags[self.params['money_fund']] = self.strategy_id
                        log.debug(f"[{self.strategy_id}] 设置货币基金策略标签: {self.params['money_fund']} -> {self.strategy_id}")
                else:
                    # 仅记录当前持有金额
                    log.info(f"[{self.strategy_id}] 冷静期持有货币基金ETF: {self.params['money_fund']} 金额: {cur_val:.2f}")
            else:
                log.info(f"[{self.strategy_id}] 冷静期持有货基：价格获取失败，跳过加仓")
        except Exception as e:
            log.warning(f"[{self.strategy_id}] 冷静期买入货基失败: {str(e)}")
    
    def _limit_flags_today(self, context, codes):
        """
        检测涨停/跌停股票（以昨收和当下价近似判定）
        
        参数:
            context: 聚宽上下文对象
            codes: 股票代码列表
        
        返回:
            dict: {'up_limit': [], 'down_limit': []}
        """
        if not codes:
            return {'up_limit': [], 'down_limit': []}
        
        today = str(context.current_dt.date())
        yday = self._get_prev_trade_day(context)
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
                
                # 计算涨停价和跌停价
                hl = self._get_today_high_limit_from_yclose(s, today, yclose)
                ll = yclose * (1.0 - self._get_limit_rate(s, today, cd[s].is_st if s in cd else False))
                
                if price >= hl - 1e-6:
                    up.append(s)
                if price <= ll + 1e-6:
                    down.append(s)
            except:
                continue
        
        return {'up_limit': list(set(up)), 'down_limit': list(set(down))}
    
    def _get_limit_rate(self, code, day_str, st_flag=False):
        """
        获取涨跌幅限制（简化版）
        
        参数:
            code: 股票代码
            day_str: 日期字符串
            st_flag: 是否ST股票
        
        返回:
            float: 涨跌幅限制（0.10表示10%）
        """
        ymd = day_str.replace('-', '') if isinstance(day_str, str) else ''
        rate = 0.10
        if code.startswith('68'):
            rate = 0.20
        elif code.startswith('3') and ymd >= '20200824':  # 创业板注册制
            rate = 0.20
        elif st_flag:
            rate = 0.05
        return rate
    
    def _get_today_high_limit_from_yclose(self, code, today_str, yclose):
        """
        根据昨日收盘价计算涨停价
        
        参数:
            code: 股票代码
            today_str: 今日日期字符串
            yclose: 昨日收盘价
        
        返回:
            float: 涨停价
        """
        cd = get_current_data()
        st_flag = False
        try:
            st_flag = bool(cd[code].is_st)
        except:
            st_flag = False
        rate = self._get_limit_rate(code, today_str, st_flag)
        return yclose * (1.0 + rate)
    
    # ==========================================================================
    # 后续任务中实现的方法
    # ==========================================================================
    
    def _get_trade_stocks(self, context, mode='sell'):
        """
        基于昨日财务+当下价格，计算当前流通市值近似，并筛选
        
        功能说明：
        1. 用当前价近似"当前流通市值"
        2. 按"当前流通市值"升序排序，取前 screen_stock_count（15只）
        3. 涨停股票过滤：剔除当前涨停的股票
        4. 已持仓中涨停的保留（不参与换仓）
        5. 返回数量控制（根据mode返回不同数量的股票）
        
        参数:
            context: 聚宽上下文对象
            mode: 模式（'sell'或'buy'）
                  - 'sell': 返回卖出模式的目标股票列表（最多down_stock_count只）
                  - 'buy': 返回买入模式的目标股票列表（最多buy_stock_count只）
        
        返回:
            list: 目标股票列表
        """
        # 检查基本面数据是否可用
        if self.df2 is None or self.df2.empty:
            log.warning(f"[{self.strategy_id}] 基本面数据为空，无法选股")
            return []
        
        df = self.df2.copy()
        cd = get_current_data()
        
        # ========== 步骤1：用当前价近似"当前流通市值" ==========
        df['curr_float_value'] = np.nan
        for code in df.index.tolist():
            try:
                px = cd[code].last_price
                if not np.isnan(px) and px > 0:
                    # circulating_market_cap 单位：亿元；乘以（当下价/昨收）近似
                    ybar = get_price(code, end_date=self.current_date, count=1, 
                                   frequency='daily', fields=['close'])
                    yclose = float(ybar['close'].iloc[-1]) if ybar is not None and not ybar.empty else px
                    scale = px / yclose if yclose > 0 else 1.0
                    df.loc[code, 'curr_float_value'] = df.loc[code, 'circulating_market_cap'] * scale
            except:
                df.loc[code, 'curr_float_value'] = np.nan
        
        # ========== 步骤2：过滤无效数据 ==========
        df = df.dropna(subset=['curr_float_value'])
        if df.empty:
            log.warning(f"[{self.strategy_id}] 过滤后无有效股票")
            return []
        
        # ========== 步骤3：按"当前流通市值"升序 + 代码排序，取前 screen_stock_count ==========
        df['code2'] = df.index
        df = df.sort_values(by=['curr_float_value', 'code2'], ascending=[True, True])
        stocks = df.head(self.params['screen_stock_count']).index.tolist()
        
        log.info(f"[{self.strategy_id}] 按流通市值筛选候选池: {len(stocks)}只")
        
        # ========== 步骤3.5：ST股票过滤：剔除ST、停牌、退市股票 ==========
        st_stocks = []
        
        for s in stocks:
            try:
                info = cd[s]
                name = info.name
                
                # 检查1：is_st标记
                if info.is_st:
                    st_stocks.append(s)
                    continue
                
                # 检查2：停牌状态
                if info.paused:
                    st_stocks.append(s)
                    continue
                
                # 检查3：名称中包含ST字符（处理编码问题）
                if name:
                    # 检查是否包含'ST'（大小写都要检查）
                    if 'ST' in name or 'st' in name or 'St' in name or 'sT' in name:
                        st_stocks.append(s)
                        continue
                    
                    # 检查是否包含'*ST'
                    if '*ST' in name or '*st' in name or '*St' in name:
                        st_stocks.append(s)
                        continue
                    
                    # 检查是否包含'退'（退市股票）
                    if '退' in name or '退市' in name:
                        st_stocks.append(s)
                        continue
                
            except Exception as e:
                log.warning(f"[{self.strategy_id}] 检查股票{s}时出错: {str(e)}")
                continue
        
        # 过滤ST股票
        if st_stocks:
            stocks = [s for s in stocks if s not in st_stocks]
            log.info(f"[{self.strategy_id}] ST股票过滤: 候选池中过滤掉{len(st_stocks)}只ST/停牌/退市股票")
        
        # ========== 步骤4：涨停过滤：剔除当前涨停的标的 ==========
        lim = self._limit_flags_today(context, stocks)
        up_limit_stock = set(lim['up_limit'])
        stocks = [s for s in stocks if s not in up_limit_stock]
        
        # ========== 步骤5：已持仓中涨停的保留（不参与换仓） ==========
        hold_codes = list(context.portfolio.positions.keys())
        lim_hold = self._limit_flags_today(context, hold_codes)
        hold_up = set(lim_hold['up_limit'])
        
        # ========== 步骤6：返回数量控制 ==========
        if mode == 'sell':
            need_num = max(0, self.params['down_stock_count'] - len(hold_up))
        else:
            need_num = max(0, self.params['buy_stock_count'] - len(hold_up))
        
        final_list = list(hold_up) + stocks[:need_num]
        
        log.info(f"[{self.strategy_id}] 选股完成: {len(final_list)}只")
        
        return final_list
    
    def buy_stocks(self, context: Any) -> None:
        """
        买入逻辑（09:31执行）
        
        功能说明：
        1. 检查是否可以买入（非空仓月、非冷静期、handle_data_flag=True）
        2. 调用_get_trade_stocks(mode='buy')获取买入目标股票列表
        3. 过滤已持仓股票，计算需要买入的股票数量
        4. 使用策略资金池资金计算每只股票的买入金额
        5. 使用order_target_value()执行买入操作
        6. 记录买入日志
        7. 更新当日买入标记
        
        参数:
            context: 聚宽上下文对象
        
        注意：
        - 使用策略资金池（self.capital_pool）而非账户现金
        - 仅在非空仓月、非冷静期、可处理数据时执行买入
        - 遵循持仓数量限制（self.params['buy_stock_count']）
        """
        # ========== 步骤1：检查是否可以处理数据 ==========
        if not self.handle_data_flag:
            return
        
        # ========== 步骤2：检查空仓月条件 ==========
        if self._is_empty_month(context):
            log.info(f"[{self.strategy_id}] 空仓月，不执行买入")
            return
        
        # ========== 步骤3：检查冷静期条件 ==========
        if self.in_cooldown and self.days_since_sell < self.params['cooldown_days']:
            log.info(f"[{self.strategy_id}] 冷静期内（第{self.days_since_sell}/{self.params['cooldown_days']}天），不执行买入")
            return
        
        # ========== 步骤4：生成应买入列表 ==========
        targets = self._get_trade_stocks(context, mode='buy')
        if not targets:
            return
        
        # ========== 步骤5：计算当前持仓和需要买入的股票数量 ==========
        # 获取当前持仓（仅统计可用持仓，持仓数量>0，且属于当前策略）
        held = []
        for c, p in context.portfolio.positions.items():
            if p.total_amount > 0:
                # 检查策略标签：只统计属于当前策略的持仓
                if hasattr(g, 'strategy_tags') and c in g.strategy_tags:
                    if g.strategy_tags[c] == self.strategy_id:
                        held.append(c)
                else:
                    # 如果没有策略标签，也计入持仓（可能是历史持仓）
                    held.append(c)
        
        # 计算需要买入的股票数量
        need_num = max(0, self.params['buy_stock_count'] - len(held))
        
        if need_num <= 0:
            return
        
        # ========== 步骤6：计算每只股票的买入金额 ==========
        # 使用策略资金池（而非账户现金）
        cash = self.capital_pool
        
        if cash <= 0:
            log.warning(f"[{self.strategy_id}] 策略资金池不足（{cash:.2f}元），无法买入")
            return
        
        # 计算每只股票的买入金额（平均分配）
        per_value = cash / float(need_num)
        
        log.info(f"[{self.strategy_id}] 买入: 持仓{len(held)}只, 目标{self.params['buy_stock_count']}只, 需买入{need_num}只, 每只{per_value:.0f}元")
        
        # ========== 步骤7：遍历目标股票，执行买入操作 ==========
        bought_count = 0
        
        for code in targets:
            # 跳过已持仓的股票
            if code in held:
                continue
            
            # 检查买入金额是否充足
            if per_value <= 0:
                break
            
            # 检查100股最小交易单位
            try:
                cd = get_current_data()
                if code in cd:
                    price = float(cd[code].last_price)
                    if price and price > 0:
                        # 计算预期股数
                        expected_shares = per_value / price
                        # 如果预期股数不足100股，调整买入金额或跳过
                        if expected_shares < 100:
                            # 计算至少买入100股需要的金额
                            min_value = price * 100
                            if cash >= min_value:
                                # 资金足够，调整买入金额为100股所需金额
                                per_value = min_value
                            else:
                                # 资金不足，跳过该股票
                                continue
            except Exception as e:
                pass
            
            # ========== 买入前检查（简化版） ==========
            # 原策略说明：技术指标验证在实盘中存在未来函数问题
            # 当前策略：基于小市值选股+波段交易，不需要额外的技术指标过滤
            # 如需启用技术指标验证，请设置 use_indicator_filter=True 并实现正确的计算逻辑
            
            # 执行买入操作
            try:
                order_target_value(code, per_value)
                log.info(f"[{self.strategy_id}] 买入: {code}")
                
                # 设置策略标签（重要：用于区分不同策略的持仓）
                if hasattr(g, 'strategy_tags'):
                    g.strategy_tags[code] = self.strategy_id
                
                # 更新状态
                held.append(code)
                need_num -= 1
                bought_count += 1
                self.today_bought_stocks.add(code)
                
                # 如果已经买够了，停止买入
                if need_num <= 0:
                    break
                    
            except Exception as e:
                log.warning(f"[{self.strategy_id}] 买入失败 {code}: {str(e)}")
        
        # ========== 步骤8：更新买入标记 ==========
        if bought_count > 0:
            self.buy_executed = True
    
    def sell_stocks(self, context: Any) -> None:
        """
        卖出逻辑（14:49执行）
        
        功能说明：
        1. 检查是否可以卖出（handle_data_flag=True）
        2. 调用_get_trade_stocks(mode='sell')获取应持仓股票列表
        3. 遍历当前持仓，卖出不在目标列表中的股票
        4. 特殊处理：
           - 冷静期内不卖出货币基金
           - 空仓月期间货币基金仅在月末卖出
           - 强制卖出ST/退市股票
        5. 记录卖出日志
        
        参数:
            context: 聚宽上下文对象
        
        注意：
        - 使用order_target()清仓（数量为0）
        - 货币基金ETF在冷静期内不卖出
        - 货币基金ETF在空仓月仅在月末卖出
        - ST/退市股票强制清仓
        """
        # ========== 步骤1：检查是否可以处理数据 ==========
        if not self.handle_data_flag:
            return
        
        # ========== 步骤2：生成应持仓列表（卖出：不在列表内的尽量卖出） ==========
        target_list = self._get_trade_stocks(context, mode='sell')
        target_set = set(target_list)
        
        # ========== 步骤3：遍历当前持仓，执行卖出操作 ==========
        sold_count = 0
        
        for code, pos in list(context.portfolio.positions.items()):
            try:
                # 检查持仓数量，跳过空持仓
                if pos.total_amount <= 0:
                    continue
                
                # 检查可平仓数量，跳过不可平仓的持仓
                closeable_amount = getattr(pos, 'closeable_amount', 0)
                if closeable_amount <= 0:
                    log.warning(f"[{self.strategy_id}] 跳过不可平仓的持仓: {code} (持仓数量: {pos.total_amount:.0f}股, 可平仓数量: {closeable_amount:.0f}股)")
                    continue
                
                # ========== 策略标签检查：只卖出属于当前策略的持仓 ==========
                if hasattr(g, 'strategy_tags') and code in g.strategy_tags:
                    stock_strategy_id = g.strategy_tags[code]
                    if stock_strategy_id != self.strategy_id:
                        # 跳过不属于当前策略的持仓
                        continue
                else:
                    # 如果没有策略标签，也跳过（可能是历史遗留持仓）
                    log.info(f"[{self.strategy_id}] 跳过无策略标签的持仓: {code}")
                    continue
                
                # ========== 特殊处理：货币基金ETF ==========
                if code == self.params['money_fund']:
                    # 冷静期期间：不卖出货币基金
                    if self.in_cooldown:
                        continue
                    
                    # 空仓月期间：货基仅在月末卖出，其余时间不卖
                    if self._is_empty_month(context):
                        if self._is_last_trading_day_in_month(context):
                            if pos.total_amount > 0:
                                order_target_value(code, 0)
                                log.info(f"[{self.strategy_id}] 空仓月月末，卖出货币基金ETF: {code}")
                                sold_count += 1
                                self.today_sold_stocks.add(code)

                                # 删除货币基金策略标签
                                if hasattr(g, 'strategy_tags') and code in g.strategy_tags:
                                    del g.strategy_tags[code]
                                continue                
                # ========== 特殊处理：ST/退市股票 ==========
                # 获取当前数据
                cd = get_current_data()[code]
                
                # 增强的ST股票检测逻辑
                is_st_stock = False
                st_reason = ""
                
                # 检查1：is_st标记
                if cd.is_st:
                    is_st_stock = True
                    st_reason = "is_st标记"
                
                # 检查2：停牌状态
                elif cd.paused:
                    is_st_stock = True
                    st_reason = "停牌"
                
                # 检查3：名称检查（处理编码问题）
                elif cd.name:
                    name = cd.name
                    # 检查是否包含'ST'（大小写都要检查）
                    if 'ST' in name or 'st' in name or 'St' in name or 'sT' in name:
                        is_st_stock = True
                        st_reason = "名称含ST"
                    # 检查是否包含'*ST'
                    elif '*ST' in name or '*st' in name or '*St' in name:
                        is_st_stock = True
                        st_reason = "名称含*ST"
                    # 检查是否包含'退'（退市股票）
                    elif '退' in name or '退市' in name:
                        is_st_stock = True
                        st_reason = "退市股票"
                
                # 强制卖出 ST/退市/停牌股票
                if is_st_stock:
                    order_target(code, 0)
                    log.warning(f"[{self.strategy_id}] 强制卖出ST/退/停牌股票: {code} - 原因: {st_reason} - 名称: {cd.name if cd.name else '未知'}")
                    sold_count += 1
                    self.today_sold_stocks.add(code)

                    # 删除策略标签
                    if hasattr(g, 'strategy_tags') and code in g.strategy_tags:
                        del g.strategy_tags[code]
                        log.debug(f"[{self.strategy_id}] 删除策略标签: {code}")
                    continue
                
                # ========== 正常卖出逻辑：不在目标列表中的股票 ==========
                # 原策略说明：卖出不在目标持仓列表中的股票
                # 技术指标验证已移除（存在未来函数问题）
                if code not in target_set:
                    order_target(code, 0)
                    log.info(f"[{self.strategy_id}] 卖出: {code}")
                    sold_count += 1
                    self.today_sold_stocks.add(code)

                    # 删除策略标签
                    if hasattr(g, 'strategy_tags') and code in g.strategy_tags:
                        del g.strategy_tags[code]
                        log.debug(f"[{self.strategy_id}] 删除策略标签: {code}")

                    # 更新卖出日期，用于冷却期检查
                    self.sold_stocks_dates[code] = str(context.current_dt.date())
                    self.last_sell_date = str(context.current_dt.date())
                    
            except Exception as e:
                log.warning(f"[{self.strategy_id}] 卖出处理异常 {code}: {str(e)}")
                # 继续尝试卖出下一只股票
        
        # ========== 步骤4：更新卖出标记 ==========
        if sold_count > 0:
            self.sell_executed = True
    
    def interval_sell_buy(self, context: Any) -> None:
        """
        分钟级风控（每分钟执行）
        
        功能说明：
        1. 空仓月或冷静期内不执行分钟风控
        2. 止盈逻辑：涨幅达到8%则清仓
        3. 回补逻辑：跌幅达到-3%且当日未买过且不在冷却期可买回
        4. 使用昨日收盘价计算涨跌幅
        5. 记录止盈和回补日志
        
        参数:
            context: 聚宽上下文对象
        
        实现参考：
        min_cooldown_swing_strategy.py 中的 interval_sell_buy 方法
        
        注意：
        - 仅在非空仓月、非冷静期时执行
        - 止盈阈值：8%（self.params['uprate']）
        - 回补阈值：-3%（self.params['downrate']）
        - 回补时需要检查冷却期状态
        - 使用order_target清仓（止盈）
        - 使用order_value按金额买入（回补）
        """
        # ========== 步骤1：检查是否在空仓月或冷静期内 ==========
        if self._is_empty_month(context) or self.in_cooldown:
            return
        
        # ========== 步骤2：获取当前数据 ==========
        cd = get_current_data()
        today_str = str(context.current_dt.date())
        
        # ========== 步骤3：止盈逻辑（涨幅达到uprate%则清仓）==========
        # 参考原始策略：不检查可平仓数量，直接执行
        
        for code, pos in list(context.portfolio.positions.items()):
            try:
                # 跳过空持仓
                if pos.total_amount <= 0:
                    continue
                
                # 跳过货币基金ETF
                if code == self.params['money_fund']:
                    continue
                
                # 检查是否已经卖出过（避免重复卖出）
                if code in self.today_sold_stocks:
                    continue
                
                # 策略标签检查：只处理属于当前策略的持仓
                if hasattr(g, 'strategy_tags') and code in g.strategy_tags:
                    stock_strategy_id = g.strategy_tags[code]
                    if stock_strategy_id != self.strategy_id:
                        continue
                
                # 获取昨日收盘价（涨跌幅基准）
                yday = self._get_prev_trade_day(context)
                ybar = get_price(code, end_date=yday, count=1, frequency='daily', fields=['close'])
                
                if ybar is None or ybar.empty:
                    continue
                
                yclose = float(ybar['close'].iloc[-1])
                
                # 获取当前价格
                last = float(cd[code].last_price) if code in cd else yclose
                
                # 计算涨跌幅
                pct = (last / yclose - 1.0) * 100.0 if yclose > 0 else 0.0
                
                # 检查是否达到止盈阈值
                if pct >= self.params['uprate']:
                    # 执行止盈：清仓
                    order_target(code, 0)
                    
                    # 更新状态
                    self.today_sold_stocks.add(code)
                    self.sold_stocks_dates[code] = today_str
                    self.last_sell_date = today_str
                    
                    # 记录日志（简洁格式，参考原始策略）
                    log.info(f'[{self.strategy_id}] 分钟止盈 卖出: {code} 涨幅: {pct:.2f}%')
            
            except Exception as e:
                pass  # 静默处理异常，避免过多日志
        
        # ========== 步骤4：回补逻辑（跌幅达到downrate%且当日未买过且不在冷却期可买回） ==========
        # 如果downrate参数为None，则不执行回补逻辑
        if self.params['downrate'] is None:
            return
        
        # 获取可用现金
        cash = context.portfolio.cash
        
        # 遍历曾经持仓的股票（可能已卖出，需要买回）
        for code in list(self.sold_stocks_dates.keys()):
            try:
                # 跳过当日已买入的股票
                if code in self.today_bought_stocks:
                    continue
                
                # 检查是否在冷静期内
                if self.in_cooldown and self.days_since_sell < self.params['cooldown_days']:
                    continue
                
                # 检查冷却期是否已过
                if not self._can_buy_after_cooldown(context, code):
                    continue
                
                # 检查当前是否持仓（避免重复买入）
                try:
                    pos = context.portfolio.positions[code]
                    if pos.total_amount > 0:
                        continue
                except:
                    pass
                
                # 检查是否是ST股票（回补时不允许买入ST股票）
                if code in cd:
                    if cd[code].is_st or cd[code].paused:
                        continue
                    if cd[code].name:
                        name = cd[code].name
                        if 'ST' in name or 'st' in name or '*ST' in name or '*st' in name:
                            continue
                        if '退' in name or '退市' in name:
                            continue
                
                # 获取昨日收盘价（涨跌幅基准）
                yday = self._get_prev_trade_day(context)
                ybar = get_price(code, end_date=yday, count=1, frequency='daily', fields=['close'])
                
                if ybar is None or ybar.empty:
                    continue
                
                yclose = float(ybar['close'].iloc[-1])
                
                # 获取当前价格
                last = float(cd[code].last_price) if code in cd else yclose
                
                # 计算涨跌幅
                pct = (last / yclose - 1.0) * 100.0 if yclose > 0 else 0.0
                
                # 检查是否达到回补阈值
                if pct <= self.params['downrate']:
                    # 计算买入金额
                    per_value = context.portfolio.total_value / float(max(1, self.params['buy_stock_count']))
                    
                    # 检查是否有足够现金
                    if per_value > 0 and cash > 0:
                        value = min(per_value, cash)
                        
                        # 执行回补：按金额买入（参考原始策略，简洁处理）
                        order_value(code, value)
                        
                        # 更新状态
                        self.today_bought_stocks.add(code)
                        cash -= value
                        
                        # 记录日志（简洁格式，参考原始策略）
                        log.info(f'[{self.strategy_id}] 分钟触发回补 买入: {code} 跌幅: {pct:.2f}% 金额: {value:.2f}')
                        
                        # 如果现金不足，停止回补
                        if cash <= 0:
                            break
                    
            except Exception as e:
                pass  # 静默处理异常，避免过多日志
    
    def _can_buy_after_cooldown(self, context, code):
        """
        检查冷却期是否已过，判断是否可以买回股票
        
        功能说明：
        1. 检查股票是否在sold_stocks_dates中
        2. 如果不在，返回True（可以买）
        3. 如果在，检查距离卖出的交易日数是否已过冷却期天数
        4. 如果已过，返回True（可以买）
        5. 否则返回False（不能买）
        
        参数:
            context: 聚宽上下文对象
            code: 股票代码
        
        返回:
            bool: 是否可以买回（True=可以，False=不能）
        
        实现参考：
        min_cooldown_swing_strategy.py 中的 _can_buy_after_cooldown 方法
        
        注意：
        - 冷却期天数：self.params['cooldown_days']
        - 按交易日计算冷却期天数，不是日历日
        - 如果股票不在sold_stocks_dates中，表示从未卖出过，可以直接买
        """
        # 如果股票不在sold_stocks_dates中，表示从未卖出过，可以直接买
        if code not in self.sold_stocks_dates:
            return True
        
        try:
            # 获取卖出日期
            last_sell_date = self.sold_stocks_dates[code]
            last = dt.datetime.strptime(last_sell_date, '%Y-%m-%d').date()
            
            # 计算交易日间隔
            start = last + timedelta(days=1)
            days = get_trade_days(start_date=start, end_date=context.current_dt.date())
            
            # 检查是否已过冷却期
            return len(days) >= self.params['cooldown_days']
            
        except Exception as e:
            # 如果计算失败，保守处理：允许买入
            log.warning(f"[{self.strategy_id}] [冷却期检查] 计算失败 {code}: {str(e)}，允许买入")
            return True
    
    def check_portfolio_decline(self, context):
        """
        检查组合跌幅，触发冷静期
        
        功能说明：
        - 检查最近3天是否连续跌幅达到return_threshold
        - 如果连续3天跌幅都≤return_threshold，则触发冷静期
        - 触发冷静期后清仓并买入货币基金
        
        参数:
            context: 聚宽上下文对象
        
        返回:
            bool: 是否触发冷静期
        
        实现参考：
        min_cooldown_swing_strategy.py 中的 check_portfolio_decline 方法
        """
        # 需要至少 4 个数据点来计算最近 3 天的跌幅
        need_num = 3
        
        if len(self.portfolio_values) < need_num + 1:
            return False
        
        decline_days = 0
        
        # 检查最近need_num天的跌幅
        for i in range(need_num):
            newer = self.portfolio_values[-(i+1)]
            older = self.portfolio_values[-(i+2)]
            
            if older > 0:
                daily_ret = (newer - older) / older
                
                # 检查是否达到跌幅阈值
                if daily_ret <= self.params['return_threshold']:
                    decline_days += 1
        
        # 如果连续need_num天都达到跌幅阈值，触发冷静期
        if decline_days >= need_num:
            # 触发冷静期：清仓并买入货基
            sold_count = 0
            for code, pos in list(context.portfolio.positions.items()):
                try:
                    # 使用safe_order确保策略标签正确设置
                    result = g.strategy_manager.safe_order(context, code, 0, self.strategy_id, 'order_target_value')
                    if result['success']:
                        sold_count += 1
                except Exception:
                    continue
            
            if sold_count > 0:
                log.info(f"[{self.strategy_id}] [组合跌幅监控] 清仓卖出: {sold_count}只股票")
            
            # 买入货币基金
            try:
                cash = context.portfolio.cash
                if cash > 0:
                    # 使用safe_order确保策略标签正确设置
                    result = g.strategy_manager.safe_order(context, self.params['money_fund'], cash, self.strategy_id, 'order_target_value')
                    if result['success']:
                        log.info(f"[{self.strategy_id}] [组合跌幅监控] 买入货币基金ETF: {self.params['money_fund']} 金额: {cash:.2f}元")
                    else:
                        log.warning(f"[{self.strategy_id}] [组合跌幅监控] 货币基金ETF买入失败: {result.get('message', '未知错误')}")
            except Exception as e:
                log.warning(f"[{self.strategy_id}] [组合跌幅监控] 买入货币基金异常: {str(e)}")
            
            # 更新冷静期状态
            self.in_cooldown = True
            self.cooldown_count += 1
            d = context.current_dt.strftime('%Y-%m-%d')
            self.cooldown_dates.append(d)
            self.last_sell_date = d
            self.days_since_sell = 0
            
            # 清空组合市值记录，避免重复触发
            self.portfolio_values = []
            
            # 记录日志
            log.info(f"[{self.strategy_id}] [组合跌幅监控] 连续{need_num}天跌幅触发冷静期")
            log.info(f"  跌幅阈值: {self.params['return_threshold']:.2%}")
            log.info(f"  冷静期次数: {self.cooldown_count}")
            log.info(f"  触发日期: {d}")
            
            return True
        
        return False
    
    def calculate_portfolio_return(self, context):
        """
        计算组合日收益
        
        功能说明：
        - 记录当日组合总市值
        - 保留最近4天的市值记录（用于计算3日连续跌幅）
        - 计算并返回日收益率
        
        参数:
            context: 聚宽上下文对象
        
        返回:
            float: 日收益率
        
        实现参考：
        min_cooldown_swing_strategy.py 中的 calculate_portfolio_return 方法
        """
        # 获取当前组合总市值
        current_total_value = context.portfolio.total_value
        
        # 记录当前市值
        self.portfolio_values.append(current_total_value)
        
        # 只保留最近4天的市值记录（用于计算3日连续跌幅）
        if len(self.portfolio_values) > 4:
            self.portfolio_values.pop(0)
        
        # 计算日收益率
        if len(self.portfolio_values) >= 2:
            yesterday_value = self.portfolio_values[-2]
            if yesterday_value > 0:
                return (current_total_value - yesterday_value) / yesterday_value
        
        return 0.0


def etf_rotation_trade(context):
    """
    ETF轮动策略交易任务（每日09:35执行）
    
    功能说明：
    - 调用test_strategy_2（ETFRotationStrategy实例）的execute_trade方法
    - 执行ETF轮动策略交易逻辑
    
    参数:
        context: 聚宽上下文对象
    """
    try:
        if hasattr(g, 'test_strategy_2') and g.test_strategy_2:
            log.info("=" * 60)
            log.info("[定时任务] etf_rotation_trade 开始执行（09:35）")
            log.info("=" * 60)
            g.test_strategy_2.execute_trade(context)
            log.info("=" * 60)
            log.info("[定时任务] etf_rotation_trade 执行完成")
            log.info("=" * 60 + "\n")
        else:
            log.warning("[定时任务] etf_rotation_trade: test_strategy_2未注册")
    except Exception as e:
        log.error(f"[定时任务] etf_rotation_trade执行失败: {str(e)}")
        import traceback
        log.error(traceback.format_exc())


