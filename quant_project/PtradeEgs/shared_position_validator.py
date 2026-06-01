# -*- coding: utf-8 -*-
"""
多策略持仓校验模块（通用可扩展设计）

功能：
1. 启动时全局校验：遍历所有策略持久化文件，进行账户-持仓一致性检查
2. 精细化清理：合法持仓保留，不合法持仓删除
3. 股票池过滤：当前策略持仓必须在策略股票池内
4. 模块化设计：独立共享模块，所有策略调用

使用方法：
    from shared_position_validator import validate_strategy_positions

    valid_positions = validate_strategy_positions(
        context,
        strategy_name='etf_rotation',
        pool_config={'type': 'static', 'value': g.etf_pool},
        owned_positions=g.owned_positions
    )

版本：v1.0
作者：AI量化交易系统
日期：2026-05-27
"""

import json
from datetime import datetime

# ========== 池校验器注册表（支持扩展） ==========

POOL_VALIDATORS = {}


def register_pool_validator(pool_type, validator_func):
    """
    注册新的池类型校验器（扩展入口）

    Args:
        pool_type: 池类型标识（如'static', 'index', 'industry', 'custom'）
        validator_func: 校验函数，签名为 func(pool_config, code) -> bool

    Example:
        def my_validator(pool_config, code):
            return code in my_custom_list

        register_pool_validator('my_type', my_validator)
    """
    POOL_VALIDATORS[pool_type] = validator_func


# ========== 内置池校验器 ==========

def _validate_static_pool(pool_config, code):
    """
    静态池校验：直接判断列表

    Args:
        pool_config: {'type': 'static', 'value': ['510300.SS', ...]}
        code: 股票代码

    Returns:
        bool: 是否在池内
    """
    pool_list = pool_config.get('value', [])
    if not isinstance(pool_list, list):
        return False
    return code in pool_list


def _validate_index_pool(pool_config, code, get_index_stocks_func=None):
    """
    指数池校验：动态查询指数成分股

    Args:
        pool_config: {'type': 'index', 'value': '399101.XBHS', 'extra': {...}}
        code: 股票代码
        get_index_stocks_func: get_index_stocks函数（PTrade API）

    Returns:
        bool: 是否在池内
    """
    if get_index_stocks_func is None:
        # 回测/模拟环境无法获取，默认通过
        return True

    index_code = pool_config.get('value', '')
    if not index_code:
        return False

    try:
        index_stocks = get_index_stocks_func(index_code)
        return code in index_stocks
    except Exception as e:
        # API调用失败，默认通过（保守策略）
        return True


def _validate_composite_pool(pool_config, code, context=None):
    """
    混合池校验：任一子池匹配即通过

    Args:
        pool_config: {'type': 'composite', 'value': [sub_config1, sub_config2, ...]}
        code: 股票代码
        context: PTrade上下文（可选，用于动态池校验）

    Returns:
        bool: 是否在任一子池内
    """
    sub_pools = pool_config.get('value', [])
    if not isinstance(sub_pools, list):
        return False

    for sub_config in sub_pools:
        if validate_pool_membership(sub_config, code, context):
            return True
    return False


def _validate_custom_pool(pool_config, code, context=None):
    """
    自定义池校验：调用用户提供的校验函数

    Args:
        pool_config: {'type': 'custom', 'extra': {'validator_func': func}}
        code: 股票代码
        context: PTrade上下文（可选）

    Returns:
        bool: 校验函数返回值
    """
    extra = pool_config.get('extra', {})
    validator_func = extra.get('validator_func')
    if validator_func is None:
        return True  # 无校验函数，默认通过

    try:
        return validator_func(code, context)
    except Exception as e:
        return True  # 校验失败，默认通过


def _validate_industry_pool(pool_config, code, get_stock_industry_func=None):
    """
    行业池校验：查询股票所属行业

    Args:
        pool_config: {'type': 'industry', 'value': ['801780', ...]}
        code: 股票代码
        get_stock_industry_func: 获取股票行业的API

    Returns:
        bool: 是否在指定行业内
    """
    if get_stock_industry_func is None:
        return True  # API不可用，默认通过

    industry_codes = pool_config.get('value', [])
    if not isinstance(industry_codes, list):
        return False

    try:
        stock_industry = get_stock_industry_func(code)
        return stock_industry in industry_codes
    except Exception as e:
        return True


# 注册内置校验器
register_pool_validator('static', _validate_static_pool)
register_pool_validator('index', _validate_index_pool)
register_pool_validator('composite', _validate_composite_pool)
register_pool_validator('custom', _validate_custom_pool)
register_pool_validator('industry', _validate_industry_pool)


# ========== 核心校验函数 ==========

def validate_pool_membership(pool_config, code, context=None):
    """
    通用池成员校验

    Args:
        pool_config: 池配置 {'type': 'xxx', 'value': xxx, 'extra': {...}}
        code: 股票代码
        context: PTrade上下文（可选，用于动态池校验）

    Returns:
        bool: 是否在池内
    """
    pool_type = pool_config.get('type', 'unknown')
    validator = POOL_VALIDATORS.get(pool_type)

    if validator is None:
        # 未知池类型，默认通过
        return True

    # 根据池类型调用相应校验器
    if pool_type == 'index':
        # 需要get_index_stocks API
        get_index_stocks_func = getattr(context, 'get_index_stocks', None) if context else None
        return validator(pool_config, code, get_index_stocks_func)
    elif pool_type == 'industry':
        # 需要get_stock_industry API
        get_stock_industry_func = getattr(context, 'get_stock_industry', None) if context else None
        return validator(pool_config, code, get_stock_industry_func)
    elif pool_type == 'composite' or pool_type == 'custom':
        # 需要context
        return validator(pool_config, code, context)
    else:
        # 静态池等，不需要额外参数
        return validator(pool_config, code)


def scan_all_state_files(all_strategy_states_data):
    """
    处理所有策略持久化数据（不使用os，数据由策略传入）

    Args:
        all_strategy_states_data: 预加载的策略数据
            {strategy_name: {'owned_positions': dict, 'pool_config': dict}}

    Returns:
        dict: {strategy_name: {'owned_positions': dict, 'pool_config': dict}}
    """
    # 直接返回传入的数据（策略负责从文件加载）
    return all_strategy_states_data if all_strategy_states_data else {}


def collect_account_positions(context):
    """
    从账户获取真实持仓

    Args:
        context: PTrade上下文

    Returns:
        dict: {code: amount}
    """
    account_positions = {}

    try:
        for code, pos in context.portfolio.positions.items():
            amount = getattr(pos, 'amount', 0)
            if amount > 0:
                account_positions[code] = amount
    except Exception as e:
        # 获取失败，返回空字典
        pass

    return account_positions


def validate_per_stock(account_positions, all_strategy_states):
    """
    逐股票校验合法性（规则1：账户份额 >= 策略份额总和）

    Args:
        account_positions: 账户真实持仓 {code: amount}
        all_strategy_states: 所有策略状态 {strategy_name: {'owned_positions': {...}}}

    Returns:
        dict: {code: {'valid': bool, 'account_amount': int, 'strategy_sum': int, 'strategies': {name: amount}}}
    """
    validation_result = {}

    # 1. 收集所有策略涉及的股票代码
    all_codes = set()
    for strategy_name, state_info in all_strategy_states.items():
        owned_positions = state_info.get('owned_positions', {})
        all_codes.update(owned_positions.keys())

    # 2. 逐股票校验
    for code in all_codes:
        # 账户份额
        account_amount = account_positions.get(code, 0)

        # 所有策略份额总和
        strategy_sum = 0
        strategy_details = {}
        for strategy_name, state_info in all_strategy_states.items():
            owned_positions = state_info.get('owned_positions', {})
            amount = owned_positions.get(code, 0)
            if amount > 0:
                strategy_sum += amount
                strategy_details[strategy_name] = amount

        # 规则1：账户份额 >= 策略份额总和
        is_valid = (account_amount >= strategy_sum)

        validation_result[code] = {
            'valid': is_valid,
            'account_amount': account_amount,
            'strategy_sum': strategy_sum,
            'strategies': strategy_details
        }

    return validation_result


def clean_current_strategy(current_strategy_name, pool_config, validation_result, context=None, log_func=None):
    """
    清理当前策略持仓，返回合法持仓

    Args:
        current_strategy_name: 当前策略名称
        pool_config: 当前策略股票池配置 {'type': 'xxx', 'value': xxx}
        validation_result: 逐股票校验结果
        context: PTrade上下文（可选，用于动态池校验）
        log_func: 日志函数（可选）

    Returns:
        dict: 合法持仓 {code: amount}
    """
    valid_positions = {}

    # 默认日志函数
    if log_func is None:
        log_func = print

    for code, result in validation_result.items():
        # 当前策略是否有该股票
        current_amount = result['strategies'].get(current_strategy_name, 0)
        if current_amount <= 0:
            continue  # 当前策略不持有该股票

        # 规则1：全局校验通过
        if not result['valid']:
            log_func("[校验] %s 账户份额%d < 策略总和%d，不合法，删除"
                     % (code, result['account_amount'], result['strategy_sum']))
            continue  # 不合法，删除

        # 规则2：股票池校验
        if not validate_pool_membership(pool_config, code, context):
            log_func("[校验] %s 不在当前策略股票池内，删除" % code)
            continue  # 不在池内，删除

        # 规则3：取min(账户实际, 持久化记录)（保守策略）
        account_amount = result['account_amount']
        final_amount = min(current_amount, account_amount)
        valid_positions[code] = final_amount
        log_func("[校验] %s 合法，保留%d股" % (code, final_amount))

    return valid_positions


# ========== 主API入口 ==========

def validate_strategy_positions(context, strategy_name, pool_config, owned_positions,
                                all_strategy_states_data=None, log_func=None, is_trade_func=None):
    """
    校验当前策略持仓（单一API入口，不依赖os模块）

    Args:
        context: PTrade上下文
        strategy_name: 策略名称（子目录名）
        pool_config: 股票池配置 {'type': 'xxx', 'value': xxx}
        owned_positions: 待校验的持仓 {code: amount}
        all_strategy_states_data: 其他策略的预加载数据（可选）
            格式: {strategy_name: {'owned_positions': {...}, 'pool_config': {...}}}
        log_func: 日志函数（可选，默认print）
        is_trade_func: 判断是否实盘的函数（可选）

    Returns:
        dict: 合法持仓 {code: amount}

    Example:
        from shared_position_validator import validate_strategy_positions

        # 简单模式：只做池校验
        g.owned_positions = validate_strategy_positions(
            context,
            g.strategy_name,
            g.pool_config,
            g.owned_positions
        )

        # 完整模式：传入其他策略数据做全局校验
        other_strategies = load_other_strategies()  # 策略自己实现
        g.owned_positions = validate_strategy_positions(
            context,
            g.strategy_name,
            g.pool_config,
            g.owned_positions,
            all_strategy_states_data=other_strategies
        )
    """
    # 默认日志函数
    if log_func is None:
        log_func = print

    # 回测模式跳过校验
    if is_trade_func is not None:
        try:
            if not is_trade_func():
                log_func("[校验] 回测模式，跳过全局校验")
                return owned_positions
        except Exception as e:
            pass  # API不可用，继续校验

    # 如果没有传入其他策略数据，只做池校验
    if all_strategy_states_data is None:
        log_func("[校验] 无其他策略数据，仅执行池校验")
        valid_positions = {}
        for code, amount in owned_positions.items():
            if validate_pool_membership(pool_config, code, context):
                valid_positions[code] = amount
                log_func("[校验-池] %s 在池内，保留" % code)
            else:
                log_func("[校验-池] %s 不在池内，删除" % code)
        return valid_positions

    # Step 1: 处理所有策略数据
    all_strategy_states = scan_all_state_files(all_strategy_states_data)

    # 将当前策略的owned_positions添加到all_strategy_states
    if strategy_name not in all_strategy_states:
        all_strategy_states[strategy_name] = {
            'owned_positions': owned_positions,
            'pool_config': pool_config
        }
    else:
        all_strategy_states[strategy_name]['owned_positions'] = owned_positions

    log_func("[校验] 收到%d个策略数据" % len(all_strategy_states))

    # Step 2: 收集账户真实持仓
    account_positions = collect_account_positions(context)
    log_func("[校验] 账户持仓: %d只" % len(account_positions))

    # Step 3: 逐股票校验
    validation_result = validate_per_stock(account_positions, all_strategy_states)

    # Step 4: 当前策略持仓清理
    valid_positions = clean_current_strategy(
        strategy_name,
        pool_config,
        validation_result,
        context,
        log_func
    )

    # 汇总日志
    original_count = len(owned_positions)
    valid_count = len(valid_positions)
    removed_count = original_count - valid_count

    log_func("[校验完成] 原持仓%d只 → 合法%d只，删除%d只"
             % (original_count, valid_count, removed_count))

    return valid_positions


# ========== 辅助函数 ==========

def get_state_dir(strategy_name, get_research_path_func, create_dir_func=None):
    """
    获取策略专属数据目录

    Args:
        strategy_name: 策略名称
        get_research_path_func: 获取研究路径的函数
        create_dir_func: 创建目录的函数（可选）

    Returns:
        str: 目录路径
    """
    try:
        base_path = get_research_path_func()
        strategy_dir = strategy_name + '/'
        full_path = base_path + strategy_dir

        # 创建目录（如果提供create_dir函数）
        if create_dir_func is not None:
            try:
                create_dir_func(strategy_dir)
            except Exception as e:
                pass  # 目录可能已存在

        return full_path
    except Exception as e:
        # API不可用，返回空字符串
        return ''


def get_state_file_path(strategy_name, get_research_path_func, create_dir_func=None):
    """
    获取状态文件路径

    Args:
        strategy_name: 策略名称
        get_research_path_func: 获取研究路径的函数
        create_dir_func: 创建目录的函数（可选）

    Returns:
        str: 文件路径
    """
    dir_path = get_state_dir(strategy_name, get_research_path_func, create_dir_func)
    if dir_path:
        return dir_path + 'state.json'
    return ''


def load_state(strategy_name, get_research_path_func, log_func=None):
    """
    加载策略持久化状态

    Args:
        strategy_name: 策略名称
        get_research_path_func: 获取研究路径的函数
        log_func: 日志函数

    Returns:
        dict: 状态字典，失败返回空字典
    """
    if log_func is None:
        log_func = print

    state_file = get_state_file_path(strategy_name, get_research_path_func)
    if not state_file:
        log_func("[持久化] 无法获取文件路径")
        return {}

    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        log_func("[持久化] 加载成功: %s" % state_file)
        return state
    except FileNotFoundError:
        log_func("[持久化] 文件不存在，首次启动")
        return {}
    except json.JSONDecodeError as e:
        log_func("[持久化] JSON解析失败: %s" % str(e))
        return {}
    except Exception as e:
        log_func("[持久化] 加载失败: %s" % str(e))
        return {}


def save_state(strategy_name, state, get_research_path_func, create_dir_func=None, log_func=None):
    """
    保存策略持久化状态

    Args:
        strategy_name: 策略名称
        state: 状态字典
        get_research_path_func: 获取研究路径的函数
        create_dir_func: 创建目录的函数（可选）
        log_func: 日志函数

    Returns:
        bool: 是否成功
    """
    if log_func is None:
        log_func = print

    state_file = get_state_file_path(strategy_name, get_research_path_func, create_dir_func)
    if not state_file:
        log_func("[持久化] 无法获取文件路径")
        return False

    try:
        # 直接写入文件（不使用os.replace）
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        log_func("[持久化] 保存成功: %s" % state_file)
        return True
    except Exception as e:
        log_func("[持久化] 保存失败: %s" % str(e))
        return False


def clear_state_file(strategy_name, get_research_path_func, log_func=None):
    """
    清空策略持久化文件（回测开始时调用）

    Args:
        strategy_name: 策略名称
        get_research_path_func: 获取研究路径的函数
        log_func: 日志函数

    Returns:
        bool: 是否成功
    """
    if log_func is None:
        log_func = print

    state_file = get_state_file_path(strategy_name, get_research_path_func)
    if not state_file:
        return False

    try:
        with open(state_file, 'w', encoding='utf-8') as f:
            f.write('{}')
        log_func("[持久化] 文件已清空: %s" % state_file)
        return True
    except Exception as e:
        log_func("[持久化] 清空失败: %s" % str(e))
        return False


# ========== 策略集成辅助 ==========

def create_default_state(strategy_name, pool_config, owned_positions, strategy_uuid=None):
    """
    创建默认状态字典（不依赖uuid模块）

    Args:
        strategy_name: 策略名称
        pool_config: 股票池配置
        owned_positions: 持仓字典
        strategy_uuid: 策略UUID（可选，策略自己生成）

    Returns:
        dict: 状态字典
    """
    return {
        'version': 2,
        'strategy_name': strategy_name,
        'strategy_uuid': strategy_uuid or '',  # 策略自己生成传入
        'saved_date': datetime.now().strftime('%Y-%m-%d'),
        'owned_positions': owned_positions,
        'pool_config': pool_config
    }


# ========== 持仓辅助函数（通用，不依赖g.*） ==========

def is_owned(code, owned_positions):
    """
    检查股票是否在策略持仓中

    Args:
        code: 股票代码
        owned_positions: 策略持仓字典 {code: amount}

    Returns:
        bool: 是否持有

    Example:
        if is_owned('510300.SS', g.owned_positions):
            # 处理持仓
    """
    return code in owned_positions


def get_owned_amount(code, context, owned_positions):
    """
    获取策略持有的实际数量（保守取min(虚拟, 实际)）

    Args:
        code: 股票代码
        context: PTrade上下文
        owned_positions: 策略持仓字典 {code: amount}

    Returns:
        int: 持有数量（虚拟和实际的较小值，防止虚拟>实际）

    Example:
        amount = get_owned_amount('510300.SS', context, g.owned_positions)
    """
    if code not in owned_positions:
        return 0

    virtual_amount = owned_positions[code]
    real_amount = 0

    try:
        if hasattr(context.portfolio, 'positions'):
            positions = context.portfolio.positions
            if code in positions:
                pos = positions[code]
                real_amount = getattr(pos, 'amount', 0)
    except Exception:
        pass

    return min(virtual_amount, real_amount)


def get_owned_enable_amount(code, context, owned_positions):
    """
    获取策略可卖数量（保守取min(虚拟, 实际可卖)）

    Args:
        code: 股票代码
        context: PTrade上下文
        owned_positions: 策略持仓字典 {code: amount}

    Returns:
        int: 可卖数量（考虑T+1限制）

    Example:
        enable = get_owned_enable_amount('510300.SS', context, g.owned_positions)
        if enable > 0:
            order(code, -enable)  # 卖出
    """
    if code not in owned_positions:
        return 0

    virtual_amount = owned_positions[code]

    try:
        if hasattr(context.portfolio, 'positions'):
            pos = context.portfolio.positions.get(code)
            if pos is None:
                return 0
            # 实际可卖数量（考虑T+1）
            real_enable = getattr(pos, 'enable_amount', getattr(pos, 'amount', 0))
            return min(virtual_amount, real_enable)
    except Exception:
        pass

    return 0


def sync_owned_positions(context, owned_positions, exclude_codes=None, log_func=None):
    """
    同步策略持仓与实际持仓（盘前调用）

    只删除已不在实际持仓中的条目，不添加新条目（防止纳入其他策略持仓）。
    更新数量为实际持仓量（保守取min）。

    Args:
        context: PTrade上下文
        owned_positions: 策略持仓字典（会被修改）
        exclude_codes: 排除代码列表（如货币基金）- 可选
        log_func: 日志函数 - 可选

    Returns:
        dict: 更新后的持仓字典（引用，原字典已被修改）

    Example:
        # 盘前同步
        g.owned_positions = sync_owned_positions(
            context,
            g.owned_positions,
            exclude_codes=[g.money_fund]  # 排除货币基金
        )

        # 无需排除
        g.owned_positions = sync_owned_positions(context, g.owned_positions)
    """
    if log_func is None:
        log_func = print

    if exclude_codes is None:
        exclude_codes = []

    removed = []
    updated = []

    for code in list(owned_positions.keys()):
        # 排除特殊代码（如货币基金）
        if code in exclude_codes:
            removed.append(code)
            del owned_positions[code]
            continue

        # 检查实际持仓
        try:
            pos = None
            if hasattr(context.portfolio, 'positions'):
                pos = context.portfolio.positions.get(code)
        except Exception:
            pos = None

        if pos is None or getattr(pos, 'amount', 0) <= 0:
            # 实际已清仓，删除虚拟记录
            removed.append(code)
            del owned_positions[code]
        else:
            # 更新数量（保守取min）
            real_amount = getattr(pos, 'amount', 0)
            if owned_positions[code] != real_amount:
                owned_positions[code] = min(owned_positions[code], real_amount)
                updated.append(code)

    # 日志输出
    if removed:
        log_func("[持仓追踪] 清理已清仓/排除: %s" % ','.join(removed))
    if updated:
        log_func("[持仓追踪] 同步数量: %s" % ','.join(updated))
    if owned_positions:
        log_func("[持仓追踪] 当前持有%d只: %s"
                 % (len(owned_positions), ','.join(owned_positions.keys())))

    return owned_positions


def check_existing_positions(context, owned_positions, strategy_uuid,
                             exclude_codes=None, log_func=None):
    """
    检查账户已有持仓（initialize()中调用，仅实盘）

    如果账户有持仓不在owned_positions中，打印警告。
    提醒用户手动清仓后再启动策略，否则策略将忽略这些持仓。

    Args:
        context: PTrade上下文
        owned_positions: 策略持仓字典
        strategy_uuid: 策略UUID（用于日志标识）
        exclude_codes: 排除代码列表（如货币基金）- 可选
        log_func: 日志函数 - 可选

    Returns:
        list: 孤立持仓代码列表（不在策略管理中的持仓）

    Example:
        # 初始化时检查
        orphan = check_existing_positions(
            context,
            g.owned_positions,
            g.strategy_uuid,
            exclude_codes=[g.money_fund],
            log_func=log.info
        )
        if orphan:
            log.warning("请手动清仓后再启动策略")
    """
    if log_func is None:
        log_func = print

    if exclude_codes is None:
        exclude_codes = []

    orphan_positions = []

    try:
        if hasattr(context.portfolio, 'positions'):
            for code, pos in context.portfolio.positions.items():
                amount = getattr(pos, 'amount', 0)
                if amount <= 0:
                    continue
                if code in exclude_codes:
                    continue
                if code not in owned_positions:
                    orphan_positions.append(code)
    except Exception:
        pass

    if orphan_positions:
        log_func("[策略UUID:%s] 检测到账户已有%d只持仓不在本策略管理中: %s"
                 % (strategy_uuid, len(orphan_positions), ','.join(orphan_positions)))
        log_func("[策略UUID:%s] 请手动清仓后再启动策略，否则策略将忽略这些持仓"
                 % strategy_uuid)

    # 打印UUID标识
    log_func("[策略UUID] %s, 持仓追踪: %d只" % (strategy_uuid, len(owned_positions)))

    return orphan_positions


# ========== 扩展状态字段辅助 ==========

def merge_state_fields(base_state, extra_fields):
    """
    合并基础状态字段和扩展字段

    Args:
        base_state: 基础状态字典（由create_default_state创建）
        extra_fields: 扩展字段字典（策略特有）

    Returns:
        dict: 合并后的状态字典

    Example:
        # 小市值策略有额外字段
        base = create_default_state('small_cap', g.pool_config, g.owned_positions, g.strategy_uuid)
        extra = {
            'in_cooldown': g.in_cooldown,
            'last_sell_date': g.last_sell_date,
            'sold_stocks_dates': g.sold_stocks_dates,
            ...
        }
        state = merge_state_fields(base, extra)
    """
    merged = base_state.copy()
    merged.update(extra_fields)
    return merged


def extract_extra_fields(state, extra_field_names):
    """
    从状态字典提取扩展字段

    Args:
        state: 加载的状态字典
        extra_field_names: 扩展字段名称列表

    Returns:
        dict: 扩展字段字典 {field_name: value}

    Example:
        # 加载时提取扩展字段
        extra = extract_extra_fields(state, [
            'in_cooldown',
            'last_sell_date',
            'sold_stocks_dates',
            ...
        ])
        g.in_cooldown = extra.get('in_cooldown', False)
        g.last_sell_date = extra.get('last_sell_date', None)
    """
    extra = {}
    for field_name in extra_field_names:
        if field_name in state:
            extra[field_name] = state[field_name]
    return extra