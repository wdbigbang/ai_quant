# 修复脚本 v2 - 处理不完整的log语句
import re

filepath = 'D:/linux/ai_quant/quant_project/PtradeEgs/multi_strategy_controller.py'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 处理不完整的log语句
# 模式1: log.info("xxx" 后面没有 % (...) 或 )
# 模式2: 孤立的 % (xxx))

lines = content.split('\n')
new_lines = []
i = 0
deleted = 0

while i < len(lines):
    line = lines[i]
    stripped = line.strip()
    
    # 检查是否是不完整的log语句开始
    if re.match(r'^\s*log\.(info|warning|error)\s*\(\s*"[^"]*"\s*$', stripped):
        # log.info("xxx") 没有闭合的格式化参数
        # 检查下一行是否是格式化参数
        if i + 1 < len(lines):
            next_stripped = lines[i + 1].strip()
            if next_stripped.startswith('% (') or next_stripped.startswith('%('):
                # 这是多行log，两行都删除
                deleted += 2
                i += 2
                continue
            elif next_stripped == ')' or next_stripped == '))':
                # 闭合括号在下一行，删除这两行
                deleted += 2
                i += 2
                continue
        # 单独的不完整log行，删除
        deleted += 1
        i += 1
        continue
    
    # 检查是否是孤立的格式化字符串
    if stripped.startswith('% (') or stripped.startswith('%('):
        deleted += 1
        i += 1
        continue
    
    # 检查是否是孤立的闭合括号（紧跟在已删除行的后面）
    if stripped == ')' or stripped == '))':
        # 检查上一行是否是log语句的开始（但可能已被处理）
        if new_lines:
            prev_stripped = new_lines[-1].strip()
            # 如果上一行以 ( 或 , 结尾，可能是不完整的语句
            if prev_stripped.endswith('(') or prev_stripped.endswith(','):
                # 删除当前行
                deleted += 1
                i += 1
                continue
    
    # 保留这一行
    new_lines.append(line)
    i += 1

# 写回
content = '\n'.join(new_lines)
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'删除了 {deleted} 行残留代码')

# 验证语法
import ast
try:
    ast.parse(content)
    print('语法检查: 通过')
    
    # 统计日志
    log_count = len([l for l in new_lines if 'log.' in l])
    print(f'剩余日志行数: {log_count}')
except SyntaxError as e:
    print(f'语法错误: {e}')
    print(f'行号: {e.lineno}')
    # 显示错误行
    error_lines = new_lines[e.lineno-3:e.lineno+3]
    for j, l in enumerate(error_lines):
        print(f'{e.lineno-3+j}: {l[:100]}')