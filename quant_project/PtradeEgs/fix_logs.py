# 修复脚本：清理孤立的格式化字符串
import re

filepath = 'D:/linux/ai_quant/quant_project/PtradeEgs/multi_strategy_controller.py'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找出并删除孤立的格式化字符串行
new_lines = []
deleted = 0

for i, line in enumerate(lines):
    stripped = line.strip()
    # 检查是否是孤立的格式化字符串（以 % 开头）
    if stripped.startswith('% (') or stripped.startswith('% (') or re.match(r'^%\s*\(', stripped):
        # 这是残留的格式化字符串，删除
        deleted += 1
        continue
    # 检查是否是空的log语句（只有log.info()或log.warning()没有内容）
    if re.match(r'^\s*log\.(info|warning|error)\s*\(\s*\)\s*$', stripped):
        deleted += 1
        continue
    # 检查是否是空的括号行
    if stripped == ')' or stripped == '))' or stripped == ') )':
        # 检查上下文，可能是残留
        if i > 0 and new_lines:
            prev_line = new_lines[-1].strip()
            # 如果前一行也是孤立的，删除当前行
            if prev_line.endswith('(') or prev_line.endswith(','):
                deleted += 1
                continue
    new_lines.append(line)

# 写回
with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f'删除了 {deleted} 行残留代码')

# 验证语法
import ast
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()
try:
    ast.parse(content)
    print('语法检查: 通过')
except SyntaxError as e:
    print(f'语法错误: {e}')
    print(f'行号: {e.lineno}')