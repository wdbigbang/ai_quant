# 安全日志简化脚本 v2
# 特点：不删除try-except块中的内容，保留结构完整

import ast
import re

filepath = 'D:/linux/ai_quant/quant_project/PtradeEgs/multi_strategy_controller.py'

# 需要删除的日志关键词（只删除函数开头的初始化日志）
DELETE_KEYWORDS = [
    '[框架-buy]', '[框架-sell]', '[框架-资金]',
    '[盘后-调试]', '[总控-订阅]', '[总控-资金]',
    '[小市值-ROE]', '[小市值-ROE改善]',
    '[ETF-动量]',
]

# 分隔线模式
SEPARATOR_PATTERNS = ['log.info("=" *', 'log.info("===']

def simplify_logs():
    """简化日志 - 只删除安全的单行日志"""
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
    in_try_except = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # 检测try-except块
        if stripped == 'try:' or stripped.startswith('try:'):
            in_try_except = True
        elif stripped == 'except' or stripped.startswith('except'):
            in_try_except = True
        elif stripped == 'finally:' or stripped.startswith('finally:'):
            in_try_except = True
        # 检测块的结束（非空行且不是缩进的）
        elif stripped and not line.startswith(' ') and not line.startswith('\t'):
            if not stripped.startswith('#') and not stripped.startswith('def') and not stripped.startswith('class'):
                in_try_except = False
        
        # 在try-except块中，不删除任何内容
        if in_try_except:
            new_lines.append(line)
            continue
        
        # 检查分隔线（安全删除）
        should_delete_sep = any(p in stripped for p in SEPARATOR_PATTERNS)
        
        # 检查是否是单行完整语句
        if should_delete_sep:
            # 统计括号
            open_parens = stripped.count('(')
            close_parens = stripped.count(')')
            if open_parens == close_parens:
                deleted_count += 1
                continue
        
        # 检查删除关键词（只删除单行）
        should_delete_kw = False
        for kw in DELETE_KEYWORDS:
            if kw in stripped:
                should_delete_kw = True
                break
        
        if should_delete_kw and 'log.' in stripped:
            # 统计括号
            open_parens = stripped.count('(')
            close_parens = stripped.count(')')
            if open_parens == close_parens:
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
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(original_content)
        return False
    
    # 写入文件
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f'删除了 {deleted_count} 行安全日志')
    remaining_log_count = len([l for l in new_lines if 'log.' in l])
    print(f'剩余日志行数: {remaining_log_count}')
    return True

if __name__ == '__main__':
    print('=' * 50)
    print('安全日志简化脚本 v2')
    print('=' * 50)
    success = simplify_logs()
    if success:
        print('简化成功！')
    else:
        print('简化失败，已回滚')