# 小市值波段策略 v5.6 - PTrade版本（多策略持仓校验模块集成）
#
# 【v5.6更新】多策略持仓校验模块集成
# - 启动时全局校验：遍历所有策略持久化文件，进行账户-持仓一致性检查
# - 精细化清理：合法持仓保留，不合法持仓删除，池外持仓删除
# - 持久化字段扩展：新增strategy_name、pool_config字段
# - 子目录名称简化：small_cap/（与strategy_name一致）
# - 动态池支持：传入指数代码，校验模块动态查询成分股
# - 回测模式跳过校验：避免无意义的全局校验开销
#
# 【v5.5更新】状态持久化+非交易日检测
# - PTrade服务器周末重启后周一initialize()重新执行，所有g.*状态丢失
# - 新增状态持久化：收盘后保存关键状态到JSON文件，initialize()时加载恢复
# - 新增非交易日检测：周末/节假日自动跳过，防止非交易日运行策略
# - 仅实盘模式生效（回测不触发，不影响回测行为）
# - 文件损坏/丢失时自动回退默认值，不崩溃
#
# 【v5.4更新】修复买入时间限制问题
# - 原问题：买入固定在09:31，模拟错过该时间点就无法买入
# - 解决方案：改为"交易时间内任意时间点执行一次"
# - 新增 g.buy_done_today 标志位控制当天只买入一次
# - 冷静期清仓和空仓月清仓在首次handle_data时立即执行
# - 保持其他逻辑不变：分钟止盈、冷静期检查（10:30/13:30/14:30）、14:49卖出
#
# 【v5.3更新】修复资金配比影响冷静期触发
#
# 【v5.3更新】修复资金配比影响冷静期触发
# - 组合跌幅检查改为只计算策略资产（股票持仓），不含现金和货币基金
# - 这样 capital_ratio 不会影响跌幅计算（股票跌4%触发，而不是总资产跌2%触发）
# - 冷静期/空仓月时跳过跌幅检查（避免持仓为空时误触发）
#
# 【v5.2更新】添加资金上限控制
# - 新增 g.capital_ratio 参数，控制策略可用资金比例
# - 买入时：strategy_capital = total_value * capital_ratio
# - 与ETF策略保持一致，支持多策略并行
#
# 【v5.1更新】日志深度简化
# - 删除冗余日志，只在关键事件打印
# - 删除未使用的函数
#
# 【v5.0更新】T+1修复 + 拆单优化
# 1. T+1修复：止盈卖出检查 pos.enable_amount（可卖数量）
# 2. 拆单优化：卖出用order+拆单，买入用order_value+拆单
#
# ==============================

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import uuid


def initialize(context):
    log.info("=" * 70)
    log.info("=== 小市值策略 v5.6 初始化（多策略持仓校验模块集成）===")

    # ===== 0. 策略信息声明（多策略校验模块使用）=====
    g.strategy_name = 'small_cap'  # 策略名称（子目录名）

    set_benchmark("000300.XSHG")

    # 指数和持仓参数
    g.index = "399101.XBHS"
    g.buy_stock_count = 7
    g.screen_stock_count = 15
    g.down_stock_count = 15

    # ===== 股票池配置（校验模块使用）=====
    g.pool_config = {'type': 'index', 'value': g.index}  # 动态池：指数成分股
    
    # ==================== 资金上限参数 ====================
    g.capital_ratio = 1.0  # 策略可用资金比例（1.0=100%，0.5=50%）
    log.info("[资金上限] 策略可用资金比例: %.0f%%" % (g.capital_ratio * 100))
    
    # ROE筛选参数
    g.roe_filter = True
    g.roe_threshold = 0
    g.roe_improve_filter = True
    g.roe_improve_top = 0.3
    
    # 风控参数
    g.uprate = 8.0              # 止盈阈值
    g.downrate = None           # 关闭回补
    g.sell_cooldown_days = 5    # 卖出后冷却天数
    g.sold_stocks_dates = {}    # {code: 'YYYY-MM-DD'}
    
    # 冷静期参数
    g.cooldown_days = 5
    g.decline_days = 3
    g.decline_threshold = -0.02
    g.empty_months = [4]     # 4 月空仓月，模拟的时候可以考虑去掉
    g.money_fund = "511880.SS"
    
    # 状态变量
    g.in_cooldown = False
    g.last_sell_date = None
    g.last_cooldown_check_time = None
    g.days_since_sell = 0
    g.cooldown_count = 0
    g.cooldown_dates = []
    
    # 组合市值记录
    g.portfolio_values = []
    
    # 当日交易记录
    g.today_bought_stocks = set()
    g.today_sold_stocks = set()
    
    # 候选股票池
    g.df2 = None
    g.current_date = None
    g.handle_data_flag = False
    
    # ==================== 昨收价（除权价体系）====================
    g.yesterday_close = {} # 昨天除权收盘价（用于涨幅计算）
    
    # ==================== 待执行操作标志位（盘前设置，首次handle_data执行）====================
    g.trigger_cooldown = False      # 触发冷静期（需要清仓买入货币基金）
    g.trigger_empty_month = False   # 触发空仓月（需要清仓买入货币基金）
    
    # ==================== 当天买入标志位（v5.4新增）====================
    g.buy_done_today = False        # 当天是否已完成买入（避免重复买入）
    g.first_handle_data_done = False  # 当天首次handle_data是否已执行（用于冷静期/空仓月清仓）

    # ==================== v5.5新增：策略UUID + 持仓归属追踪 ====================
    g.strategy_uuid = uuid.uuid4().hex[:8]  # 策略唯一标识（首次生成，_load_state会覆盖）
    g.owned_positions = {}                   # {code: amount} 只追踪本策略买入的持仓

    if not is_trade():
        set_backtest()

    # ==================== v5.5新增：加载持久化状态 ====================
    # PTrade服务器周末重启后周一initialize()重新执行，需要从文件恢复状态
    _load_state(context)

    # ==================== v5.6新增：全局持仓校验 ====================
    # 仅实盘模式执行（校验模块已移除os依赖）
    if is_trade():
        try:
            # 添加策略目录到Python搜索路径（解决导入失败问题）
            import sys
            sys.path.insert(0, get_research_path())
            from shared_position_validator import validate_strategy_positions
            g.owned_positions = validate_strategy_positions(
                context,
                g.strategy_name,
                g.pool_config,
                g.owned_positions,
                log_func=log.info,
                is_trade_func=is_trade
            )
            # 保存校验后的合法持仓
            _save_state(context)
        except Exception as e:
            log.warning("[校验] 校验模块调用失败: %s，使用原始持仓" % str(e))

    # ==================== 检查账户已有持仓（警告日志）====================
    _check_existing_positions(context)

    log.info("[参数] 指数: %s" % g.index)
    log.info("[参数] 持仓数量: %d, 筛选数量: %d" % (g.buy_stock_count, g.screen_stock_count))
    log.info("[参数] ROE筛选: %s, 阈值: %s" % (g.roe_filter, g.roe_threshold))
    log.info("[参数] ROE改善筛选: %s, 比例: %.0f%%" % (g.roe_improve_filter, g.roe_improve_top * 100))
    log.info("[参数] 止盈阈值: %.1f%%" % g.uprate)
    log.info("[参数] 冷静期: %d天, 连续跌幅: %d天, 跌幅阈值: %.2f%%" % (g.cooldown_days, g.decline_days, g.decline_threshold * 100))
    log.info("[参数] 空仓月份: %s" % str(g.empty_months))
    log.info("[参数] 货币基金: %s" % g.money_fund)
    log.info("=" * 70)


def set_backtest():
    set_limit_mode("UNLIMITED")
    set_commission(commission_ratio=0.0003, min_commission=5.0)
    set_slippage(slippage=0.002)


# ============================================================
#                    辅助函数
# ============================================================

def _get_prev_trade_day(context):
    """获取昨日日期字符串"""
    return context.previous_date


def _get_state_file_path():
    """获取状态持久化文件路径（独立子目录）"""
    base_path = get_research_path()
    strategy_dir = "small_cap/"  # 简化目录名（策略名称）
    create_dir(strategy_dir)
    return base_path + strategy_dir + "state.json"


def _save_state(context):
    """
    保存策略状态到JSON文件

    仅实盘模式执行，回测模式跳过。
    收盘后调用，保存关键变量。
    """
    if not is_trade():
        return

    state = {
        'version': 2,  # 版本升级（支持校验模块）
        'strategy_name': g.strategy_name,  # 策略名称（新增）
        'pool_config': g.pool_config,  # 股票池配置（新增）
        'saved_date': context.blotter.current_dt.strftime('%Y-%m-%d'),
        'in_cooldown': g.in_cooldown,
        'last_sell_date': g.last_sell_date,
        'sold_stocks_dates': g.sold_stocks_dates,
        'cooldown_count': g.cooldown_count,
        'cooldown_dates': g.cooldown_dates,
        'portfolio_values': g.portfolio_values,
        'strategy_uuid': g.strategy_uuid,
        'owned_positions': g.owned_positions,
    }

    try:
        state_path = _get_state_file_path()
        # 直接写入文件（PTrade禁止使用os.replace）
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        log.info("[状态持久化] 保存成功: cooldown=%s, last_sell=%s"
                 % (g.in_cooldown, g.last_sell_date))
    except Exception as e:
        log.warning("[状态持久化] 保存失败: %s" % str(e))


def _load_state(context):
    """
    从JSON文件加载策略状态（带验证和过期清理）

    仅实盘模式执行，回测模式跳过。
    在initialize()中调用，覆盖默认值恢复上交易日状态。
    文件不存在/损坏/版本不匹配 → 使用默认值，不崩溃。
    """
    if not is_trade():
        log.info("[状态持久化] 回测模式，跳过状态加载")
        return

    try:
        state_path = _get_state_file_path()
        # 直接尝试打开文件（FileNotFoundError会被捕获）
        with open(state_path, 'r', encoding='utf-8') as f:
            state = json.load(f)

        # 版本检查（兼容version 1和version 2）
        version = state.get('version', 0)
        if version not in [1, 2]:
            log.warning("[状态持久化] 版本不匹配(v%s)，使用默认值"
                        % version)
            return

        saved_date = state.get('saved_date', '')
        log.info("[状态持久化] 加载状态(v%d): saved_date=%s" % (version, saved_date))

        # 恢复状态变量（带类型验证）
        g.in_cooldown = bool(state.get('in_cooldown', False))
        g.last_sell_date = state.get('last_sell_date', None)

        loaded_sold = state.get('sold_stocks_dates', {})
        if isinstance(loaded_sold, dict):
            g.sold_stocks_dates = loaded_sold
        else:
            g.sold_stocks_dates = {}

        g.cooldown_count = int(state.get('cooldown_count', 0))

        loaded_dates = state.get('cooldown_dates', [])
        if isinstance(loaded_dates, list):
            g.cooldown_dates = loaded_dates
        else:
            g.cooldown_dates = []

        loaded_values = state.get('portfolio_values', [])
        if isinstance(loaded_values, list) and len(loaded_values) <= 4:
            g.portfolio_values = loaded_values
        else:
            g.portfolio_values = []

        # 清理过期sold_stocks_dates（超过2×cooldown_days日历天）
        current_trading_day = get_trading_day(0)
        expired_keys = []
        for code, sell_date_str in g.sold_stocks_dates.items():
            try:
                sell_date = datetime.strptime(sell_date_str, '%Y-%m-%d').date()
                days_elapsed = (current_trading_day - sell_date).days
                if days_elapsed > g.sell_cooldown_days * 2:
                    expired_keys.append(code)
            except Exception:
                expired_keys.append(code)

        for code in expired_keys:
            del g.sold_stocks_dates[code]

        if expired_keys:
            log.info("[状态持久化] 清理过期卖出记录: %d只" % len(expired_keys))

        # 恢复UUID和持仓归属
        loaded_uuid = state.get('strategy_uuid', '')
        if loaded_uuid:
            g.strategy_uuid = loaded_uuid
        log.info("[策略UUID] 恢复: %s" % g.strategy_uuid)

        loaded_owned = state.get('owned_positions', {})
        if isinstance(loaded_owned, dict):
            g.owned_positions = loaded_owned
        else:
            g.owned_positions = {}

        # version 2新增字段
        if version >= 2:
            loaded_name = state.get('strategy_name')
            if loaded_name:
                g.strategy_name = loaded_name
            loaded_pool = state.get('pool_config')
            if loaded_pool and isinstance(loaded_pool, dict):
                g.pool_config = loaded_pool

        log.info("[状态持久化] 恢复成功: cooldown=%s, last_sell=%s, cooldown_count=%d, portfolio_values=%d条, owned=%d只"
                 % (g.in_cooldown, g.last_sell_date, g.cooldown_count, len(g.portfolio_values), len(g.owned_positions)))

    except (json.JSONDecodeError, ValueError) as e:
        log.warning("[状态持久化] 状态文件损坏，使用默认值: %s" % str(e))
    except Exception as e:
        log.warning("[状态持久化] 加载失败，使用默认值: %s" % str(e))


def _is_owned(code):
    """检查代码是否在本策略的owned_positions中"""
    return code in g.owned_positions


def _get_owned_amount(code, context):
    """获取本策略持有的实际数量（min(虚拟, 实际)，防止虚拟>实际）"""
    if code not in g.owned_positions:
        return 0
    virtual_amount = g.owned_positions[code]
    real_amount = 0
    if code in context.portfolio.positions:
        real_amount = context.portfolio.positions[code].amount
    return min(virtual_amount, real_amount)


def _get_owned_enable_amount(code, context):
    """获取本策略持有的可卖数量（min(虚拟可卖, 实际可卖)）"""
    if code not in g.owned_positions:
        return 0
    virtual_amount = g.owned_positions[code]
    pos = context.portfolio.positions.get(code)
    if pos is None:
        return 0
    real_enable = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
    return min(virtual_amount, real_enable)


def _sync_owned_positions(context):
    """
    同步owned_positions与实际持仓（盘前调用）

    只删除已不在实际持仓中的条目，不添加新条目（防止纳入其他策略持仓）。
    更新数量为实际持仓量（保守取min）。
    """
    removed = []
    updated = []
    for code in list(g.owned_positions.keys()):
        if code not in context.portfolio.positions or context.portfolio.positions[code].amount <= 0:
            removed.append(code)
            del g.owned_positions[code]
        elif code == g.money_fund:
            # 货币基金由冷静期/空仓月管理，不纳入持仓追踪
            removed.append(code)
            del g.owned_positions[code]
        else:
            real_amount = context.portfolio.positions[code].amount
            if g.owned_positions[code] != real_amount:
                g.owned_positions[code] = min(g.owned_positions[code], real_amount)
                updated.append(code)

    if removed:
        log.info("[持仓追踪] 清理已清仓: %s" % ','.join(removed))
    if updated:
        log.info("[持仓追踪] 同步数量: %s" % ','.join(updated))
    if g.owned_positions:
        log.info("[持仓追踪] 当前持有%d只: %s" % (len(g.owned_positions), ','.join(g.owned_positions.keys())))


def _check_existing_positions(context):
    """
    检查账户已有持仓（仅实盘，initialize()中调用）

    如果账户有非货币基金持仓且不在owned_positions中，打印警告。
    提醒用户手动清仓后再启动策略。
    """
    if not is_trade():
        return

    orphan_positions = []
    for code, pos in context.portfolio.positions.items():
        if pos.amount <= 0:
            continue
        if code == g.money_fund:
            continue
        if code not in g.owned_positions:
            orphan_positions.append(code)

    if orphan_positions:
        log.warning("[策略UUID:%s] 检测到账户已有%d只持仓不在本策略管理中: %s"
                    % (g.strategy_uuid, len(orphan_positions), ','.join(orphan_positions)))
        log.warning("[策略UUID:%s] 请手动清仓后再启动策略，否则策略将忽略这些持仓"
                    % g.strategy_uuid)

    # 打印UUID标识
    log.info("[策略UUID] %s, 持仓追踪: %d只" % (g.strategy_uuid, len(g.owned_positions)))


def _filter_st_pause_delist(codes):
    """过滤ST/停牌/退市股票"""
    if not codes:
        return []
    try:
        return filter_stock_by_status(codes, filter_type=["ST", "HALT", "DELISTING"])
    except Exception as e:
        log.error("[过滤] 失败: %s" % str(e))
        return codes


def _get_universe(context):
    """获取股票池"""
    try:
        pool = get_index_stocks(g.index)
        return _filter_st_pause_delist(pool)
    except Exception as e:
        log.error("[股票池] 失败: %s" % str(e))
        return []


def _get_limit_rate(code, st_flag=False):
    """涨跌幅限制比例"""
    rate = 0.10
    if code.startswith('68'):  # 科创板
        rate = 0.20
    elif code.startswith('3'):  # 创业板
        rate = 0.20
    elif st_flag:
        rate = 0.05
    return rate


def _limit_flags_today(context, codes):
    """判断涨停（简化版，使用check_limit）"""
    if not codes:
        return {'up_limit': [], 'down_limit': []}
    
    up, down = [], []
    for s in codes:
        try:
            limit_info = check_limit(s)
            if limit_info and s in limit_info:
                if limit_info[s] == 1:
                    up.append(s)
                elif limit_info[s] == -1:
                    down.append(s)
        except:
            pass
    
    return {'up_limit': up, 'down_limit': down}


def _trading_days_since_last_sell(context):
    """计算距离上次卖出的交易日数"""
    if not g.last_sell_date:
        return 0
    try:
        last = datetime.strptime(g.last_sell_date, '%Y-%m-%d').date()
        current = context.blotter.current_dt.date()
        return (current - last).days
    except:
        return 0


def _is_empty_month(context):
    """检查是否是空仓月"""
    try:
        mon = context.blotter.current_dt.month
        return mon in g.empty_months
    except:
        return False


def _is_first_trading_day_in_month(context):
    """检查是否是月初第一个交易日"""
    try:
        cur = context.blotter.current_dt.date()
        month_start = cur.replace(day=1)
        return cur.day <= 3
    except:
        return False


def _is_last_trading_day_in_month(context):
    """检查是否是月末最后一个交易日"""
    try:
        cur = context.blotter.current_dt.date()
        return cur.day >= 28
    except:
        return False


def _execute_cooldown_clear(context, data):
    """
    执行冷静期清仓（在首次handle_data时执行）
    
    逻辑：
    1. 清仓所有股票持仓（拆单卖出）
    2. 买入货币基金（避险）
    
    注：已从buy_stocks移出，避免错过09:31无法执行的问题
    """
    current_time = context.blotter.current_dt.strftime('%H:%M')
    log.info("[%s] 冷静期清仓..." % current_time)

    # 只清仓本策略的持仓，不影响其他策略或手动交易
    for code in list(g.owned_positions.keys()):
        try:
            enable_amount = _get_owned_enable_amount(code, context)
            if enable_amount > 0:
                remaining = enable_amount
                while remaining > 0:
                    batch = min(remaining, 900000)
                    batch = int(batch / 100) * 100
                    if batch > 0:
                        order(code, -batch)
                        remaining -= batch
                    else:
                        if remaining > 0:
                            order(code, -remaining)
                            break
                # 从持仓追踪中删除
                del g.owned_positions[code]
                log.info("[冷静期] 卖出 %s: %d股" % (code, enable_amount))
        except Exception as e:
            log.error("[冷静期] 卖出失败 %s: %s" % (code, str(e)))

    cash = context.portfolio.cash
    if cash > 0:
        try:
            order_value(g.money_fund, cash)
            log.info("[冷静期] 买入货基 %.2f" % cash)
        except Exception as e:
            log.error("[冷静期] 买入货基失败: %s" % str(e))


def _execute_empty_month_clear(context, data):
    """
    执行空仓月清仓（在首次handle_data时执行）
    
    逻辑：
    1. 清仓所有股票持仓（拆单卖出，保留货币基金）
    2. 买入货币基金（避险）
    
    注：已从buy_stocks移出，避免错过09:31无法执行的问题
    """
    current_time = context.blotter.current_dt.strftime('%H:%M')
    log.info("[%s] 空仓月清仓..." % current_time)

    # 只清仓本策略的持仓，不影响其他策略或手动交易
    for code in list(g.owned_positions.keys()):
        try:
            enable_amount = _get_owned_enable_amount(code, context)
            if enable_amount > 0:
                remaining = enable_amount
                while remaining > 0:
                    batch = min(remaining, 900000)
                    batch = int(batch / 100) * 100
                    if batch > 0:
                        order(code, -batch)
                        remaining -= batch
                    else:
                        if remaining > 0:
                            order(code, -remaining)
                            break
                # 从持仓追踪中删除
                del g.owned_positions[code]
                log.info("[空仓月] 卖出 %s: %d股" % (code, enable_amount))
        except Exception as e:
            log.error("[空仓月] 卖出失败 %s: %s" % (code, str(e)))
    
    cash = context.portfolio.cash
    if cash > 0:
        try:
            order_value(g.money_fund, cash)
            log.info("[空仓月] 买入货基 %.2f" % cash)
        except Exception as e:
            log.error("[空仓月] 买入货基失败: %s" % str(e))


def _get_strategy_assets(context, data):
    """
    计算策略资产（只计算本策略owned_positions中的持仓市值）

    用于组合跌幅检查，只计算本策略相关的资产变化：
    - 策略资产 = owned_positions持仓市值
    - 不含现金、货币基金、其他策略持仓、手动交易持仓

    返回：策略资产市值（元）
    """
    total = 0.0
    for code in g.owned_positions:
        amount = _get_owned_amount(code, context)
        if amount <= 0:
            continue
        # 获取当前价格
        try:
            if code in data:
                price = data[code].price
            else:
                his = get_history(1, frequency='1d', field='close', security_list=code, fq=None, include=False, is_dict=True)
                if his and code in his:
                    price = float(his[code]['close'][-1])
                else:
                    price = 0
            if price > 0:
                total += amount * price
        except:
            pass
    return total


# ============================================================
#                    ROE计算（保留）
# ============================================================

def _get_financial_data(stock_list, start_year, end_year):
    """获取财报数据"""
    try:
        np_df = get_fundamentals(stock_list, "income_statement",
                                  fields=["np_parent_company_owners"],
                                  start_year=start_year, end_year=end_year)
        eq_df = get_fundamentals(stock_list, "balance_statement",
                                  fields=["total_shareholder_equity"],
                                  start_year=start_year, end_year=end_year)
        
        if np_df is None or np_df.empty or eq_df is None or eq_df.empty:
            return None
        
        if isinstance(np_df.index, pd.MultiIndex):
            np_reset = np_df.reset_index()
            eq_reset = eq_df.reset_index()
        else:
            return None
        
        np_reset = np_reset.rename(columns={'np_parent_company_owners': 'np'})
        eq_reset = eq_reset.rename(columns={'total_shareholder_equity': 'equity'})
        
        merged = pd.merge(
            np_reset[['secu_code', 'end_date', 'np']],
            eq_reset[['secu_code', 'end_date', 'equity']],
            on=['secu_code', 'end_date'], how='inner'
        )
        return merged
    except Exception as e:
        log.error("[财报] 获取失败: %s" % str(e))
        return None


def _calc_single_quarter_roe(financial_df):
    """计算单季度ROE"""
    if financial_df is None or financial_df.empty:
        return None
    
    results = []
    grouped = financial_df.groupby('secu_code')
    
    for stock, group in grouped:
        date_data = {}
        for _, row in group.iterrows():
            parts = row['end_date'].split('-')
            year, month = int(parts[0]), int(parts[1])
            date_data[(year, month)] = {
                'np': row['np'], 'equity': row['equity'], 'end_date': row['end_date']
            }
        
        for (year, month), d in date_data.items():
            curr_np, curr_equity, end_date = d['np'], d['equity'], d['end_date']
            
            if month == 3:
                single_np = curr_np
            elif month == 6:
                if (year, 3) in date_data:
                    single_np = curr_np - date_data[(year, 3)]['np']
                else: continue
            elif month == 9:
                if (year, 6) in date_data:
                    single_np = curr_np - date_data[(year, 6)]['np']
                else: continue
            elif month == 12:
                if (year, 9) in date_data:
                    single_np = curr_np - date_data[(year, 9)]['np']
                else: continue
            else:
                continue
            
            roe = (single_np / curr_equity) * 100 if curr_equity > 0 else 0
            results.append({'secu_code': stock, 'end_date': end_date, 'roe': roe})
    
    return pd.DataFrame(results) if results else None


def _get_latest_quarter_date(current_date):
    """获取最近的财报季度"""
    year = int(str(current_date)[:4])
    month = int(str(current_date)[5:7])
    
    if month <= 3: return "%d-09-30" % (year - 1)
    elif month <= 6: return "%d-12-31" % (year - 1)
    elif month <= 9: return "%d-06-30" % year
    else: return "%d-09-30" % year


def _filter_by_roe(context, stock_list):
    """ROE筛选"""
    if not stock_list:
        return []
    
    try:
        current_year = int(str(g.current_date)[:4])
        financial_df = _get_financial_data(stock_list, str(current_year - 1), str(current_year))
        
        if financial_df is None or financial_df.empty:
            return stock_list
        
        roe_df = _calc_single_quarter_roe(financial_df)
        if roe_df is None or roe_df.empty:
            return stock_list
        
        latest_quarter = _get_latest_quarter_date(g.current_date)
        roe_quarter = roe_df[roe_df['end_date'] == latest_quarter].copy()
        
        if roe_quarter.empty:
            roe_df = roe_df.sort_values('end_date', ascending=False)
            roe_quarter = roe_df.drop_duplicates(subset='secu_code', keep='first')
        
        roe_quarter = roe_quarter.set_index('secu_code')
        roe_quarter = roe_quarter[roe_quarter['roe'] > g.roe_threshold]
        
        return roe_quarter.index.tolist()
    except Exception as e:
        log.error("[ROE] 失败: %s" % str(e))
        return stock_list


def _filter_by_roe_improve(context, stock_list):
    """ROE改善筛选"""
    if not stock_list:
        return []
    
    try:
        current_year = int(str(g.current_date)[:4])
        financial_df = _get_financial_data(stock_list, str(current_year - 3), str(current_year))
        
        if financial_df is None or financial_df.empty:
            return stock_list
        
        roe_df = _calc_single_quarter_roe(financial_df)
        if roe_df is None or roe_df.empty:
            return stock_list
        
        latest_quarter = _get_latest_quarter_date(g.current_date)
        all_dates = sorted(roe_df['end_date'].unique())
        
        if latest_quarter in all_dates:
            latest_idx = all_dates.index(latest_quarter)
            latest_5 = all_dates[max(0, latest_idx-4):latest_idx+1] if latest_idx >= 4 else all_dates[-5:]
        else:
            latest_5 = all_dates[-5:]
        
        if len(latest_5) < 5:
            return stock_list
        
        roe_pivot = roe_df.pivot_table(index='secu_code', columns='end_date', values='roe')
        
        # 过滤ROE异常
        for d in latest_5:
            if d in roe_pivot.columns:
                roe_pivot = roe_pivot[(roe_pivot[d].abs() <= 100) | (roe_pivot[d].isna())]
        
        # 计算改善值
        roe_pivot['increase'] = 4 * roe_pivot[latest_5[4]] - roe_pivot[latest_5[0]] - \
                                roe_pivot[latest_5[1]] - roe_pivot[latest_5[2]] - roe_pivot[latest_5[3]]
        
        roe_pivot = roe_pivot.dropna(subset=['increase'])
        roe_pivot = roe_pivot.sort_values(by='increase', ascending=False)
        
        top_count = max(1, int(len(roe_pivot) * g.roe_improve_top))
        return roe_pivot.head(top_count).index.tolist()
    except Exception as e:
        log.error("[ROE改善] 失败: %s" % str(e))
        return stock_list


# ============================================================
#                    盘前选股
# ============================================================

def before_trading_start(context, data):
    """盘前处理"""

    # ==================== v5.5新增：非交易日检测 ====================
    # PTrade服务器周末重启后可能在非交易日拉起策略，需要跳过执行
    # get_trading_day(0)在非交易日返回上一交易日，与当前日期不同即非交易日
    if is_trade():
        try:
            current_date = context.blotter.current_dt.date()
            trading_day = get_trading_day(0)
            if current_date != trading_day:
                log.warning("[盘前] %s 是非交易日（交易日=%s），跳过执行"
                           % (current_date, trading_day))
                g.handle_data_flag = False
                g.buy_done_today = True
                return
        except Exception as e:
            log.warning("[盘前] 非交易日检测异常，继续执行: %s" % str(e))

    g.today_bought_stocks = set()
    g.today_sold_stocks = set()
    g.current_date = _get_prev_trade_day(context)
    g.handle_data_flag = True

    # ==================== v5.5新增：同步持仓归属 ====================
    _sync_owned_positions(context)

    # ==================== v5.4新增：每天重置买入标志位 ====================
    g.buy_done_today = False
    g.first_handle_data_done = False
    
    if g.in_cooldown:
        g.days_since_sell = _trading_days_since_last_sell(context)
    
    date_str = context.blotter.current_dt.strftime('%Y-%m-%d')
    
    # 空仓月处理
    if _is_empty_month(context):
        if _is_first_trading_day_in_month(context):
            g.trigger_empty_month = True
            log.info("[盘前] %s 空仓月开始" % date_str)
        g.df2 = None
        owned_held = [c for c in g.owned_positions if _get_owned_amount(c, context) > 0]
        log.info("[盘前铃声] %s | 总资产=%.2f 现金=%.2f | 本策略持仓%d只 | 空仓月"
                 % (date_str, context.portfolio.portfolio_value, context.portfolio.cash, len(owned_held)))
        return

    # 冷静期处理
    if g.in_cooldown:
        log.info("[盘前] %s 冷静期 %d/%d" % (date_str, g.days_since_sell, g.cooldown_days))
        g.df2 = None
        owned_held = [c for c in g.owned_positions if _get_owned_amount(c, context) > 0]
        log.info("[盘前铃声] %s | 总资产=%.2f 现金=%.2f | 本策略持仓%d只 | 冷静期%d/%d"
                 % (date_str, context.portfolio.portfolio_value, context.portfolio.cash,
                    len(owned_held), g.days_since_sell, g.cooldown_days))
        return
    
    # 盘前预存昨除权价
    g.yesterday_close = {}
    # 只获取本策略持仓的昨收价，不包含其他策略或手动交易的持仓
    hold_codes = [code for code in g.owned_positions if _get_owned_amount(code, context) > 0]
    
    for code in hold_codes:
        try:
            his = get_history(1, frequency='1d', field='close', security_list=code, fq=None, include=False, is_dict=True)
            if his and code in his:
                yclose = float(his[code]['close'][-1])
                if yclose > 0:
                    g.yesterday_close[code] = yclose
        except:
            pass
    
    # ==================== 组合跌幅检查（只计算策略资产）====================
    # 【v5.3修复】用策略资产（股票持仓市值）计算跌幅，而不是总资产
    # 这样 capital_ratio 不会影响跌幅计算
    # 冷静期/空仓月时跳过跌幅检查（持仓可能为空或只有货币基金）
    
    if g.in_cooldown or _is_empty_month(context):
        # 冷静期/空仓月时跳过跌幅检查，清空记录
        g.portfolio_values = []
    else:
        # 计算策略资产（股票持仓市值，排除货币基金）
        strategy_assets = _get_strategy_assets(context, data)
        g.portfolio_values.append(strategy_assets)
        if len(g.portfolio_values) > 4:
            g.portfolio_values.pop(0)
        
        if check_portfolio_decline(context):
            g.df2 = None
            return
    
    # ==================== 选股流程 ====================
    stock_pool = _get_universe(context)
    log.info("[选股] 指数成分: %d只" % len(stock_pool))
    if not stock_pool:
        log.warning("[选股] 股票池为空")
        g.df2 = None
        return

    # ROE筛选
    if g.roe_filter:
        before_roe = len(stock_pool)
        stock_pool = _filter_by_roe(context, stock_pool)
        log.info("[选股] ROE筛选: %d只 → %d只" % (before_roe, len(stock_pool)))
        if not stock_pool:
            g.df2 = None
            return

    # ROE改善筛选
    if g.roe_improve_filter:
        before_roe_improve = len(stock_pool)
        stock_pool = _filter_by_roe_improve(context, stock_pool)
        log.info("[选股] ROE改善筛选: %d只 → %d只" % (before_roe_improve, len(stock_pool)))
        if not stock_pool:
            g.df2 = None
            return
    
    # 获取市值数据
    try:
        df = get_fundamentals(stock_pool, "valuation", 
                              fields=["float_value", "a_floats"],
                              date=g.current_date)
        if df is None or df.empty:
            g.df2 = None
            return
        
        if isinstance(df.index, pd.MultiIndex):
            df_reset = df.reset_index()
            df_reset = df_reset.sort_values(by='end_date', ascending=False)
            df = df_reset.drop_duplicates(subset='secu_code', keep='first')
            df = df.set_index('secu_code')
        
        # PTrade的float_value单位是元，转换成亿元
        df['float_value'] = df['float_value'] / 100000000.0
        
        g.df2 = df
        
        # 【关键】PTrade需要订阅股票池
        stock_codes = list(g.df2.index)
        set_universe(stock_codes)
        
        log.info("[选股] 最终数量: %d" % len(g.df2))

        # ==================== 盘前铃声汇总 ====================
        owned_held = [c for c in g.owned_positions if _get_owned_amount(c, context) > 0]
        strategy_assets = _get_strategy_assets(context, data)
        log.info("[盘前铃声] %s | 总资产=%.2f 策略资产=%.2f 现金=%.2f | 本策略持仓%d只: %s | 选标=%d只"
                 % (date_str, context.portfolio.portfolio_value, strategy_assets, context.portfolio.cash,
                    len(owned_held), ','.join(owned_held) if owned_held else '空仓', len(g.df2)))
    except Exception as e:
        log.error("[选股] 市值数据失败: %s" % str(e))
        g.df2 = None


# ============================================================
#                    分钟回调（时间分发）
# ============================================================

def handle_data(context, data):
    """
    分钟回调 - 时间分发（v5.4改进）
    
    【买入逻辑改进】
    - 原逻辑：固定09:31买入，模拟错过就无法买入
    - 新逻辑：交易时间内任意时间点执行一次（用g.buy_done_today控制）
    - 冷静期清仓/空仓月清仓在首次handle_data时立即执行
    
    【时间分发】
    - 14:49 卖出（sell_stocks）- 固定时间
    - 10:30/13:30/14:30 冷静期检查 - 固定时间
    - 其他时间：分钟风控（interval_sell_buy）+ 买入（首次执行）
    
    注：组合跌幅检查已移至 before_trading_start（v4.7修复）
    """
    hour = context.blotter.current_dt.hour
    minute = context.blotter.current_dt.minute
    time_str = "%02d:%02d" % (hour, minute)
    
    # ==================== 14:49 固定卖出 ====================
    if time_str == '14:49':
        sell_stocks(context, data)
        return
    
    # ==================== 冷静期检查（固定时间点）====================
    if time_str in ['10:30', '13:30', '14:30']:
        check_and_clean_stocks_in_cooldown(context, data)
        return
    
    # ==================== 首次handle_data：执行冷静期/空仓月清仓 ====================
    if not g.first_handle_data_done:
        g.first_handle_data_done = True
        
        # 执行冷静期清仓
        if g.trigger_cooldown:
            _execute_cooldown_clear(context, data)
            g.trigger_cooldown = False
            return
        
        # 执行空仓月清仓
        if g.trigger_empty_month:
            _execute_empty_month_clear(context, data)
            g.trigger_empty_month = False
            return
    
    # ==================== 买入逻辑：交易时间内任意时间点执行一次 ====================
    # 条件：交易时间内（09:30-14:40）+ 未完成买入 + handle_data_flag
    if '09:30' <= time_str <= '14:40' and not g.buy_done_today and g.handle_data_flag:
        buy_stocks(context, data)
        return
    
    # ==================== 其他时间：分钟风控 ====================
    interval_sell_buy(context, data)


# ============================================================
#                    买入函数
# ============================================================

def buy_stocks(context, data):
    """买入逻辑（交易时间内任意时间点执行一次）- v5.4改进"""
    
    # ==================== 检查是否已完成买入 ====================
    if g.buy_done_today:
        return
    
    if not g.handle_data_flag:
        return
    
    # 空仓月/冷静期不买入股票
    if _is_empty_month(context) or (g.in_cooldown and g.days_since_sell < g.cooldown_days):
        return
    
    # 获取目标股票
    targets = _get_trade_stocks(context, data, mode='buy')
    if not targets:
        g.buy_done_today = True  # 无目标股票也标记为完成
        return
    
    # 已持仓（只计算本策略owned_positions中的持仓）
    held = [code for code in g.owned_positions if _get_owned_amount(code, context) > 0]
    need_num = g.buy_stock_count - len(held)
    
    if need_num <= 0:
        g.buy_done_today = True  # 已满仓也标记为完成
        return
    
    # ==================== 资金上限计算 ====================
    total_value = context.portfolio.total_value
    strategy_capital = total_value * g.capital_ratio
    per_value = strategy_capital / float(g.buy_stock_count) if g.buy_stock_count > 0 else 0
    
    current_time = context.blotter.current_dt.strftime('%H:%M')
    log.info("[%s] 买入: 总资产%.2f, 策略资金%.2f(%.0f%%), 每只%.2f" 
             % (current_time, total_value, strategy_capital, g.capital_ratio * 100, per_value))
    log.info("[%s] 已持仓%d, 需买入%d" % (current_time, len(held), need_num))
    
    bought_count = 0
    for code in targets:
        if code in held:
            continue
        if per_value <= 0:
            break
        try:
            price = data[code].price if code in data else 0
            if price <= 0:
                continue
            
            max_value_per_order = 900000 * price * 0.95
            remaining_value = per_value
            while remaining_value > 0:
                batch_value = min(remaining_value, max_value_per_order)
                if batch_value > 0:
                    order_value(code, batch_value)
                    remaining_value -= batch_value
                else:
                    break
            
            g.today_bought_stocks.add(code)
            held.append(code)
            need_num -= 1
            bought_count += 1

            # ==================== v5.5新增：记录买入到持仓追踪 ====================
            estimated_shares = int(per_value / price / 100) * 100 if price > 0 else 0
            if estimated_shares > 0:
                g.owned_positions[code] = estimated_shares

            log.info("[买入] %s: 价格=%.2f, 预估%.2f元/%d股" % (code, price, per_value, estimated_shares))
            
            # 买入后存储昨除权价
            if code not in g.yesterday_close:
                try:
                    his = get_history(1, frequency='1d', field='close', security_list=code, fq=None, include=False, is_dict=True)
                    if his and code in his:
                        yclose = float(his[code]['close'][-1])
                        if yclose > 0:
                            g.yesterday_close[code] = yclose
                except:
                    pass
            
            if need_num <= 0:
                break
        except Exception as e:
            log.error("[买入] %s 失败: %s" % (code, str(e)))
    
    if bought_count > 0:
        log.info("[%s] 完成: 买入%d只" % (current_time, bought_count))
    
    # ==================== 标记当天买入完成 ====================
    g.buy_done_today = True


# ============================================================
#                    卖出函数
# ============================================================

def sell_stocks(context, data):
    """卖出逻辑（14:49）- 拆单版本"""
    
    if not g.handle_data_flag:
        return
    
    # 获取目标股票
    targets = _get_trade_stocks(context, data, mode='sell')
    target_set = set(targets)
    
    sold_count = 0
    # 只遍历本策略的持仓，不处理其他策略或手动交易的持仓
    for code in list(g.owned_positions.keys()):
        try:
            enable_amount = _get_owned_enable_amount(code, context)
            if enable_amount <= 0:
                continue

            # 货币基金处理（货币基金不在owned_positions中，由冷静期/空仓月管理）
            if code == g.money_fund:
                continue

            # 不在目标列表中则卖出
            if code not in target_set:
                log.info("[卖出] %s: 不在目标列表, 可卖%d股" % (code, enable_amount))
                remaining = enable_amount
                while remaining > 0:
                    batch = min(remaining, 900000)
                    batch = int(batch / 100) * 100
                    if batch > 0:
                        order(code, -batch)
                        remaining -= batch
                    else:
                        if remaining > 0:
                            order(code, -remaining)
                        break

                g.today_sold_stocks.add(code)
                g.last_sell_date = context.blotter.current_dt.strftime('%Y-%m-%d')
                sold_count += 1
                # 从持仓追踪中删除
                if code in g.owned_positions:
                    del g.owned_positions[code]
        except Exception as e:
            log.error('[卖出] %s 异常: %s' % (code, str(e)))
    
    if sold_count > 0:
        log.info("[14:49] 完成: 卖出%d只" % sold_count)

    # ==================== 空仓月最后交易日：卖出货基（退出空仓月）====================
    # 货币基金不在g.owned_positions中，需要单独处理
    # v5.4原逻辑：空仓月最后交易日的14:49卖出货基，5月才能重新买入股票
    if _is_empty_month(context) and _is_last_trading_day_in_month(context):
        if not g.in_cooldown and g.money_fund in context.portfolio.positions:
            try:
                pos = context.portfolio.positions[g.money_fund]
                enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
                if enable_amount >= 100:
                    remaining = enable_amount
                    while remaining > 0:
                        batch = min(remaining, 900000)
                        batch = int(batch / 100) * 100
                        if batch > 0:
                            order(g.money_fund, -batch)
                            remaining -= batch
                        else:
                            if remaining > 0:
                                order(g.money_fund, -remaining)
                            break
                    log.info("[14:49] 空仓月月末，卖出货基%d股" % enable_amount)
            except Exception as e:
                log.error('[卖出] 空仓月月末卖货基失败: %s' % str(e))


# ============================================================
#                    获取交易股票
# ============================================================

def _get_trade_stocks(context, data, mode='sell'):
    """获取交易股票列表（简化版）"""
    if g.df2 is None or g.df2.empty:
        return []
    
    df = g.df2.copy()
    
    # 用当前价近似"当前流通市值"
    df['curr_float_value'] = np.nan
    stock_codes = df.index.tolist()
    
    # 获取昨日收盘价
    try:
        his = get_history(1, frequency='1d', field='close', security_list=stock_codes, fq='pre', include=False, is_dict=True)
    except Exception as e:
        log.error("[选股] get_history失败: %s" % str(e))
        return []
    
    for code in stock_codes:
        try:
            if his is None or code not in his:
                continue
            
            yclose = float(his[code]['close'][-1])
            if yclose <= 0:
                continue
            
            # 尝试从data获取当前价，如果不行就用昨收价
            try:
                px = data[code].price if code in data else yclose
            except:
                px = yclose
            
            if px <= 0:
                continue
            
            # 当前流通市值 = 原市值 * 缩放因子
            scale = px / yclose
            df.loc[code, 'curr_float_value'] = df.loc[code, 'float_value'] * scale
        except:
            pass
    
    df = df.dropna(subset=['curr_float_value'])
    
    if df.empty:
        return []
    
    # 按市值排序（升序，小市值优先）
    df = df.sort_values(by='curr_float_value', ascending=True)
    stocks = df.head(g.screen_stock_count).index.tolist()
    
    # 涨停过滤
    lim = _limit_flags_today(context, stocks)
    up_limit_stock = set(lim['up_limit'])
    stocks = [s for s in stocks if s not in up_limit_stock]
    
    # 已持仓中涨停的保留
    hold_codes = list(g.owned_positions.keys())
    lim_hold = _limit_flags_today(context, hold_codes)
    hold_up = set(lim_hold['up_limit'])
    
    # 返回数量
    if mode == 'sell':
        need_num = max(0, g.down_stock_count - len(hold_up))
    else:
        need_num = max(0, g.buy_stock_count - len(hold_up))
    
    return list(hold_up) + stocks[:need_num]


# ============================================================
#                    分钟风控
# ============================================================

def interval_sell_buy(context, data):
    """分钟级风控（止盈）- 使用除权价体系 + T+1检查 + 拆单"""
    # 空仓月或冷静期内不执行
    if _is_empty_month(context) or g.in_cooldown:
        return
    
    today_str = str(context.blotter.current_dt.date())
    
    for code in list(g.owned_positions.keys()):
        try:
            amount = _get_owned_amount(code, context)
            if amount <= 0:
                continue

            # ==================== T+1检查：使用enable_amount ====================
            enable_amount = _get_owned_enable_amount(code, context)

            if enable_amount <= 0:
                continue

            # ==================== 涨幅计算（除权价体系）====================
            yclose = g.yesterday_close.get(code, 0)

            if yclose <= 0:
                continue

            # 当前除权价
            if code not in data:
                continue

            current_price = data[code].price

            # 涨幅 = 当前除权价 / 昨除权价 - 1
            pct = (current_price / yclose - 1.0) * 100.0

            # 止盈（只在触发时打印）
            if pct >= g.uprate and code not in g.today_sold_stocks:
                log.info('[止盈触发] %s: 昨收=%.3f, 当前=%.3f, 涨幅=%.2f%%, 可卖=%d股'
                         % (code, yclose, current_price, pct, enable_amount))

                # ==================== 拆单卖出 ====================
                remaining = enable_amount
                while remaining > 0:
                    batch = min(remaining, 900000)
                    batch = int(batch / 100) * 100
                    if batch > 0:
                        order(code, -batch)
                        remaining -= batch
                    else:
                        if remaining > 0:
                            order(code, -remaining)
                        break

                g.today_sold_stocks.add(code)
                g.sold_stocks_dates[code] = today_str
                g.last_sell_date = today_str
                # 从持仓追踪中删除
                if code in g.owned_positions:
                    del g.owned_positions[code]
                log.info("[止盈] %s: 已下单卖出%d股" % (code, enable_amount))
        except Exception as e:
            log.error('分钟止盈处理失败 %s: %s' % (code, str(e)))


# ============================================================
#                    组合跌幅与冷静期
# ============================================================

def check_portfolio_decline(context):
    """
    检查策略资产连续下跌（只在触发时打印）
    
    【v5.3修复】只计算策略资产（股票持仓市值）的跌幅
    - 不含现金和货币基金
    - capital_ratio 不会影响跌幅计算
    
    例如：capital_ratio=0.5 时
    - 股票跌4% -> 策略资产跌4% -> 触发冷静期（正确）
    - 而不是：股票跌4% -> 总资产跌2% -> 不触发（错误）
    """
    need_num = g.decline_days
    
    if len(g.portfolio_values) < need_num + 1:
        return False
    
    # 检查是否有足够的策略资产记录
    # 如果持仓为空（策略资产=0），跳过检查
    if g.portfolio_values[-1] <= 0:
        return False
    
    decline_days = 0
    decline_details = []
    
    for i in range(need_num):
        newer = g.portfolio_values[-(i+1)]
        older = g.portfolio_values[-(i+2)]
        if older > 0:
            daily_ret = (newer - older) / older
            is_decline = daily_ret <= g.decline_threshold
            decline_details.append({
                'day': i+1, 'new': newer, 'old': older, 
                'ret': daily_ret, 'trigger': is_decline
            })
            if is_decline:
                decline_days += 1
    
    if decline_days >= need_num:
        log.info('=' * 50)
        log.info('[冷静期触发] 策略资产连续%d天跌幅超阈值%.2f%%' % (need_num, g.decline_threshold * 100))
        for detail in decline_details:
            log.info("  第%d天: 策略资产 %.2f -> %.2f, 跌幅=%.2f%%" 
                     % (detail['day'], detail['old'], detail['new'], detail['ret'] * 100))
        
        g.trigger_cooldown = True
        g.in_cooldown = True
        g.cooldown_count += 1
        d = context.blotter.current_dt.strftime('%Y-%m-%d')
        g.cooldown_dates.append(d)
        g.last_sell_date = d
        g.days_since_sell = 0
        g.portfolio_values = []
        
        log.info('[冷静期] 日期: %s, 累计次数: %d' % (d, g.cooldown_count))
        log.info('=' * 50)
        return True
    return False


def check_and_clean_stocks_in_cooldown(context, data):
    """冷静期管理（拆单版本）"""
    if not g.in_cooldown:
        return
    
    g.days_since_sell = _trading_days_since_last_sell(context)
    
    # 到期退出
    if g.days_since_sell >= g.cooldown_days:
        log.info("[冷静期] 到期退出 (%d天)" % g.cooldown_days)
        try:
            if g.money_fund in context.portfolio.positions:
                pos = context.portfolio.positions[g.money_fund]
                enable_amount = pos.enable_amount if hasattr(pos, 'enable_amount') else pos.amount
                if enable_amount >= 100:
                    log.info("[冷静期] 到期退出, 卖出货基%d股" % enable_amount)
                    remaining = enable_amount
                    while remaining > 0:
                        batch = min(remaining, 900000)
                        batch = int(batch / 100) * 100
                        if batch > 0:
                            order(g.money_fund, -batch)
                            remaining -= batch
                        else:
                            if remaining > 0:
                                order(g.money_fund, -remaining)
                            break
        except Exception as e:
            log.error('[冷静期] 卖出货基失败: %s' % str(e))
        g.in_cooldown = False
        return
    
    # 冷静期内清空本策略的股票持仓
    sold_codes = []
    for code in list(g.owned_positions.keys()):
        try:
            enable_amount = _get_owned_enable_amount(code, context)
            if enable_amount > 0:
                remaining = enable_amount
                while remaining > 0:
                    batch = min(remaining, 900000)
                    batch = int(batch / 100) * 100
                    if batch > 0:
                        order(code, -batch)
                        remaining -= batch
                    else:
                        if remaining > 0:
                            order(code, -remaining)
                        break
                sold_codes.append(code)
                del g.owned_positions[code]
                log.info("[冷静期检查] 卖出 %s: %d股" % (code, enable_amount))
        except Exception as e:
            log.error('[冷静期] 卖出失败 %s: %s' % (code, str(e)))
    
    # 买入货币基金
    cash = context.portfolio.cash
    if cash >= 10000:
        try:
            order_value(g.money_fund, cash)
        except Exception as e:
            log.error('[冷静期] 买入货基失败: %s' % str(e))
    
    if sold_codes:
        log.info("[冷静期] 天数%d/%d, 清仓%d只" % (g.days_since_sell, g.cooldown_days, len(sold_codes)))


# ============================================================
#                    盘后处理
# ============================================================

def after_trading_end(context, data):
    """盘后处理"""
    # 同步owned_positions中的实际数量（保守取min）
    for code in list(g.owned_positions.keys()):
        if code in context.portfolio.positions:
            real_amount = context.portfolio.positions[code].amount
            g.owned_positions[code] = min(g.owned_positions[code], real_amount)

    positions = context.portfolio.positions
    hold_count = len([p for p in positions.values() if p.amount > 0])
    owned_count = len([c for c in g.owned_positions if context.portfolio.positions.get(c) and context.portfolio.positions[c].amount > 0])
    log.info("[盘后] 账户持仓%d只, 本策略持仓%d只, 总资产%.2f, 现金%.2f"
             % (hold_count, owned_count, context.portfolio.portfolio_value, context.portfolio.cash))

    # ==================== 当日交易汇总 ====================
    bought_list = sorted(g.today_bought_stocks)
    sold_list = sorted(g.today_sold_stocks)
    log.info("[盘后汇总] 今日买入%d只: %s | 卖出%d只: %s"
             % (len(bought_list), ','.join(bought_list) if bought_list else '无',
                len(sold_list), ','.join(sold_list) if sold_list else '无'))

    # ==================== v5.5新增：保存持久化状态 ====================
    _save_state(context)