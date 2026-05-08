# 日志简化脚本 v2
# 一次性处理整个文件，避免多次edit导致内容漂移

KEEP_PATTERNS = [
    # 保留的关键业务日志（正则匹配）
    r'log\.info\("[总控] 初始化',        # 启动初始化
    r'log\.info\("[小市值] 选股',         # 选股完成
    r'log\.info\("[小市值] 买入',         # 买入完成  
    r'log\.info\("[小市值] 14:49',        # 调仓卖出
    r'log\.info\("[小市值] 止盈',         # 止盈触发
    r'log\.info\("[小市值] 冷静期',       # 冷静期触发/退出
    r'log\.info\("[小市值] 空仓月',       # 空仓月
    r'log\.info\("[盘后]',                # 盘后总结（一行）
    r'log\.info\("[ETF]',                 # ETF关键日志
]

DELETE_PATTERNS = [
    # 删除的调试日志模式（包含这些关键词的日志行全部删除）
    '[框架-buy]',
    '[框架-sell]',
    '[框架-资金]',
    '[盘后-调试]',
    '[总控-订阅]',
    '[总控-资金]',
    '[小市值-盘前]',
    '[小市值-选股]',
    '[小市值-ROE]',
    '[小市值-ROE改善]',
    '[小市值-买入]',
    '[小市值-调试]',
    '[ETF-动量]',
    '[ETF-卖出]',
    '[ETF-买入]',
    '[ETF-调试]',
    'log.info("=" *',
    'log.info("===',
    'log.warning("[框架',
    'log.error("[框架',
]

def should_keep_line(line):
    """判断是否保留这一行"""
    # 如果不是日志行，保留
    if 'log.' not in line:
        return True
    
    # 检查是否匹配保留模式
    import re
    for pattern in KEEP_PATTERNS:
        if re.search(pattern, line):
            return True
    
    # 检查是否匹配删除模式
    for pattern in DELETE_PATTERNS:
        if pattern in line:
            return False
    
    # 其他日志行保留（如止盈、卖出等关键操作）
    return True

def simplify_file(filepath):
    """简化日志"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    deleted_count = 0
    
    for line in lines:
        if should_keep_line(line):
            new_lines.append(line)
        else:
            deleted_count += 1
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    return deleted_count

if __name__ == '__main__':
    filepath = 'D:/linux/ai_quant/quant_project/PtradeEgs/multi_strategy_controller.py'
    deleted = simplify_file(filepath)
    print(f'日志简化完成，删除了 {deleted} 行调试日志')