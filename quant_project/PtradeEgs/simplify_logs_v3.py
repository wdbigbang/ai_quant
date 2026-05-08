# 日志简化脚本 v3 - 确保删除完整的log语句
# 更精确的处理方式

def simplify_logs(filepath):
    """简化日志，确保删除完整语句"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 删除模式的日志关键词
    DELETE_KEYWORDS = [
        '[框架-buy]', '[框架-sell]', '[框架-资金]',
        '[盘后-调试]', '[总控-订阅]', '[总控-资金]',
        '[小市值-盘前]', '[小市值-选股]', '[小市值-ROE]', '[小市值-ROE改善]',
        '[小市值-买入]', '[小市值-调试]', '[小市值-盘后]',
        '[ETF-动量]', '[ETF-卖出]', '[ETF-买入]', '[ETF-调试]',
    ]
    
    # 分隔线模式
    SEPARATOR_PATTERNS = ['log.info("="', 'log.info("===']
    
    new_lines = []
    skip_until_closing = False
    deleted_count = 0
    
    for i, line in enumerate(lines):
        # 如果正在跳过多行log语句
        if skip_until_closing:
            if ')' in line and ')' in line.strip().split('log.')[-1] if 'log.' in line else True:
                # 找到闭合括号，结束跳过
                skip_until_closing = False
            deleted_count += 1
            continue
        
        # 检查是否是分隔线
        is_separator = any(p in line for p in SEPARATOR_PATTERNS)
        
        # 检查是否包含删除关键词
        should_delete = False
        for kw in DELETE_KEYWORDS:
            if kw in line:
                should_delete = True
                break
        
        # 如果是分隔线或包含删除关键词
        if is_separator or should_delete:
            # 检查这是否是多行log语句的开始
            if 'log.info' in line or 'log.warning' in line or 'log.error' in line:
                # 检查是否在这一行闭合
                stripped = line.strip()
                # 统计括号
                open_parens = stripped.count('(')
                close_parens = stripped.count(')')
                if open_parens > close_parens:
                    # 多行语句，需要跳过后续行
                    skip_until_closing = True
                deleted_count += 1
                continue
            else:
                # 不是log行但包含关键词（注释等），保留
                new_lines.append(line)
        else:
            # 正常保留
            new_lines.append(line)
    
    # 写回文件
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    return deleted_count

if __name__ == '__main__':
    import sys
    filepath = 'D:/linux/ai_quant/quant_project/PtradeEgs/multi_strategy_controller.py'
    deleted = simplify_logs(filepath)
    print(f'删除了 {deleted} 行日志')
    
    # 验证语法
    import ast
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    try:
        ast.parse(content)
        print('语法检查: 通过')
    except SyntaxError as e:
        print(f'语法错误: {e}')