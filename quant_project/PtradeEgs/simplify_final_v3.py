# 安全日志简化脚本 v3 - 分多次运行，每次删除一部分
import ast

filepath = 'D:/linux/ai_quant/quant_project/PtradeEgs/multi_strategy_controller.py'

# 第一次：删除调试类日志
DELETE_ROUND_1 = [
    '[框架-buy]', '[框架-sell]', '[框架-资金]',
    '[盘后-调试]', '[总控-订阅]', '[总控-资金]',
]

# 第二次：删除选股过程日志
DELETE_ROUND_2 = [
    '[小市值-ROE]', '[小市值-ROE改善]',
    '[小市值-选股]',
]

# 第三次：删除ETF过程日志
DELETE_ROUND_3 = [
    '[ETF-动量]',
]

# 第四次：删除分隔线
SEPARATOR_PATTERNS = ['log.info("=" *', 'log.info("===']

def run_simplify_round(delete_keywords, round_name):
    """运行一轮简化"""
    with open(filepath, 'r', encoding='utf-8') as f:
        original_content = f.read()
    
    try:
        ast.parse(original_content)
    except SyntaxError as e:
        print(f'原始文件语法错误: {e}')
        return 0, False
    
    lines = original_content.split('\n')
    new_lines = []
    deleted = 0
    
    for line in lines:
        stripped = line.strip()
        should_delete = False
        
        # 检查关键词
        for kw in delete_keywords:
            if kw in stripped and 'log.' in stripped:
                # 只删除单行完整语句
                open_p = stripped.count('(')
                close_p = stripped.count(')')
                if open_p == close_p:
                    should_delete = True
                    break
        
        # 检查分隔线
        for p in SEPARATOR_PATTERNS:
            if p in stripped:
                open_p = stripped.count('(')
                close_p = stripped.count(')')
                if open_p == close_p:
                    should_delete = True
                    break
        
        if should_delete:
            deleted += 1
        else:
            new_lines.append(line)
    
    new_content = '\n'.join(new_lines)
    
    try:
        ast.parse(new_content)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return deleted, True
    except SyntaxError as e:
        print(f'{round_name} 语法错误，跳过: {e}')
        return 0, False

if __name__ == '__main__':
    print('=' * 50)
    print('安全日志简化脚本 v3')
    print('=' * 50)
    
    total_deleted = 0
    
    # 运行多轮
    rounds = [
        (DELETE_ROUND_1, '第1轮-调试日志'),
        (DELETE_ROUND_2, '第2轮-选股日志'),
        (DELETE_ROUND_3, '第3轮-ETF日志'),
    ]
    
    for keywords, name in rounds:
        deleted, success = run_simplify_round(keywords, name)
        if success:
            print(f'{name}: 删除{deleted}行')
            total_deleted += deleted
        else:
            print(f'{name}: 跳过')
    
    # 最终统计
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    log_count = len([l for l in content.split('\n') if 'log.' in l])
    total_lines = len(content.split('\n'))
    
    print('=' * 50)
    print(f'总共删除: {total_deleted}行')
    print(f'剩余日志: {log_count}行')
    print(f'剩余总行数: {total_lines}')
    print('简化完成！')