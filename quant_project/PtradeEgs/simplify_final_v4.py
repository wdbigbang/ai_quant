# 安全日志简化脚本 v4 - 智能识别安全位置
import ast

filepath = 'D:/linux/ai_quant/quant_project/PtradeEgs/multi_strategy_controller.py'

DELETE_KEYWORDS = [
    '[框架-buy]', '[框架-sell]', '[框架-资金]',
    '[总控-订阅]', '[总控-资金]',
    '[小市值-盘前]', '[小市值-买入]',
    '[ETF-卖出]', '[ETF-买入]',
]

def simplify():
    with open(filepath, 'r', encoding='utf-8') as f:
        original = f.read()
    
    try:
        ast.parse(original)
    except:
        print('原始语法错误')
        return False
    
    lines = original.split('\n')
    new_lines = []
    deleted = 0
    
    # 遍历每一行
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # 如果不是log行，直接保留
        if 'log.' not in stripped:
            new_lines.append(line)
            continue
        
        # 检查是否在try/except/finally块中
        # 向上查找最近的try/except/finally关键字
        in_block = False
        for j in range(max(0, i-20), i):
            prev = lines[j].strip()
            if prev == 'try:' or prev.startswith('try:'):
                in_block = True
                break
            if prev.startswith('except') or prev == 'except:':
                in_block = True
                break
            if prev.startswith('finally') or prev == 'finally:':
                in_block = True
                break
            # 非缩进行表示块结束
            if prev and not lines[j].startswith(' ') and not lines[j].startswith('\t'):
                if prev.startswith('def ') or prev.startswith('class ') or prev.startswith('#'):
                    continue
                in_block = False
                break
        
        # 如果在try-except块中，保留
        if in_block:
            new_lines.append(line)
            continue
        
        # 检查是否应该删除
        should_delete = False
        for kw in DELETE_KEYWORDS:
            if kw in stripped:
                # 检查是否是单行完整语句
                open_p = stripped.count('(')
                close_p = stripped.count(')')
                if open_p == close_p:
                    should_delete = True
                    break
        
        # 分隔线也删除
        if 'log.info("=" *' in stripped or 'log.info("=== ' in stripped:
            open_p = stripped.count('(')
            close_p = stripped.count(')')
            if open_p == close_p:
                should_delete = True
        
        if should_delete:
            deleted += 1
        else:
            new_lines.append(line)
    
    new_content = '\n'.join(new_lines)
    
    try:
        ast.parse(new_content)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'删除了 {deleted} 行')
        remaining = len([l for l in new_lines if 'log.' in l])
        print(f'剩余日志: {remaining} 行')
        return True
    except SyntaxError as e:
        print(f'语法错误: {e}')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(original)
        print('已回滚')
        return False

if __name__ == '__main__':
    print('=' * 50)
    print('安全日志简化脚本 v4')
    print('=' * 50)
    simplify()