# 日志简化脚本 - 改为注释而不是删除
import ast

filepath = 'D:/linux/ai_quant/quant_project/PtradeEgs/multi_strategy_controller.py'

# 要注释掉的日志关键词
COMMENT_KEYWORDS = [
    '[框架-buy]', '[框架-sell]', '[框架-资金]',
    '[总控-订阅]', '[总控-资金]',
    '[小市值-ROE]', '[小市值-ROE改善]', '[小市值-选股]', '[小市值-盘前]', '[小市值-买入]',
    '[ETF-动量]', '[ETF-卖出]', '[ETF-买入]',
]

def comment_logs():
    with open(filepath, 'r', encoding='utf-8') as f:
        original = f.read()
    
    try:
        ast.parse(original)
        print('原始语法: 正确')
    except:
        print('原始语法错误')
        return False
    
    lines = original.split('\n')
    new_lines = []
    commented = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # 检查是否需要注释
        should_comment = False
        for kw in COMMENT_KEYWORDS:
            if kw in stripped and 'log.' in stripped:
                should_comment = True
                break
        
        # 分隔线也注释
        if 'log.info("=" *' in stripped or 'log.info("=== ' in stripped:
            should_comment = True
        
        if should_comment:
            # 找到log.的位置，在其前面加#
            if 'log.' in stripped:
                # 计算缩进
                indent = len(line) - len(line.lstrip())
                # 注释掉整行
                new_line = ' ' * indent + '# ' + line.lstrip()
                new_lines.append(new_line)
                commented += 1
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    new_content = '\n'.join(new_lines)
    
    try:
        ast.parse(new_content)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'注释了 {commented} 行日志')
        remaining = len([l for l in new_lines if 'log.' in l and not l.strip().startswith('#')])
        print(f'剩余有效日志: {remaining} 行')
        return True
    except SyntaxError as e:
        print(f'语法错误: {e}')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(original)
        print('已回滚')
        return False

if __name__ == '__main__':
    print('=' * 50)
    print('日志简化脚本 - 注释模式')
    print('=' * 50)
    comment_logs()