# 安全日志简化脚本
# 特点：只删除单行log，保留多行语句完整，出错自动回滚

import ast
import re

filepath = 'D:/linux/ai_quant/quant_project/PtradeEgs/multi_strategy_controller.py'

# 需要删除的日志关键词（单行日志）
DELETE_KEYWORDS = [
    '[框架-buy]', '[框架-sell]', '[框架-资金]',
    '[盘后-调试]', '[总控-订阅]', '[总控-资金]',
    '[小市值-盘前]', '[小市值-选股]', '[小市值-ROE]', '[小市值-ROE改善]',
    '[小市值-买入]', '[小市值-调试]',
    '[ETF-动量]', '[ETF-卖出]', '[ETF-买入]', '[ETF-调试]',
]

# 分隔线模式
SEPARATOR_PATTERNS = ['log.info("=" *', 'log.info("===']

def is_single_line_log(line):
    """判断是否是单行完整的log语句"""
    stripped = line.strip()
    if not ('log.info' in stripped or 'log.warning' in stripped or 'log.error' in stripped):
        return False
    
    # 统计括号数量
    open_parens = stripped.count('(')
    close_parens = stripped.count(')')
    
    # 如果括号匹配，说明是单行语句
    return open_parens == close_parens

def should_delete(line):
    """判断是否应该删除这一行"""
    stripped = line.strip()
    
    # 检查分隔线
    for p in SEPARATOR_PATTERNS:
        if p in stripped:
            return True
    
    # 检查删除关键词
    for kw in DELETE_KEYWORDS:
        if kw in stripped:
            return True
    
    return False

def simplify_logs():
    """简化日志"""
    # 读取文件
    with open(filepath, 'r', encoding='utf-8') as f:
        original_content = f.read()
    
    # 验证原始文件语法
    try:
        ast.parse(original_content)
        print('原始文件语法: 正确')
    except SyntaxError as e:
        print(f'原始文件有语法错误: {e}')
        return False
    
    lines = original_content.split('\n')
    new_lines = []
    deleted_count = 0
    
    for line in lines:
        # 只删除单行log且包含删除关键词的行
        if is_single_line_log(line) and should_delete(line):
            deleted_count += 1
            continue
        
        # 删除分隔线（即使是多行也删除整个语句）
        if any(p in line for p in SEPARATOR_PATTERNS):
            deleted_count += 1
            continue
        
        # 其他行保留
        new_lines.append(line)
    
    # 构建新内容
    new_content = '\n'.join(new_lines)
    
    # 验证新文件语法
    try:
        ast.parse(new_content)
        print('简化后语法: 正确')
    except SyntaxError as e:
        print(f'简化后有语法错误: {e}')
        print('自动回滚...')
        # 回滚
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(original_content)
        return False
    
    # 写入文件
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f'删除了 {deleted_count} 行单行日志')
    
    # 统计剩余日志
    remaining_log_count = len([l for l in new_lines if 'log.' in l])
    print(f'剩余日志行数: {remaining_log_count}')
    print(f'剩余总行数: {len(new_lines)}')
    
    return True

if __name__ == '__main__':
    print('=' * 50)
    print('安全日志简化脚本')
    print('=' * 50)
    success = simplify_logs()
    if success:
        print('简化成功！')
    else:
        print('简化失败，已回滚')