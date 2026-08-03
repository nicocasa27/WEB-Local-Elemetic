# Targeted cleanup - remove ONLY specific artifact lines
with open(r'C:\Users\Usuario\Documents\trae_projects\DJANGO WEB\catalogos\views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
removed = 0
for i, line in enumerate(lines):
    stripped = line.strip()
    # Only remove lines that are EXACTLY HTML/XML/tool artifacts
    if stripped in ('</invoke>', '</parameter>', '</invoke>',
                   'file_path', 'old_str', 'new_str', 'old_str', 'new_str',
                   'file_path', 'file_path', 'file_path',
                   'old_str', 'new_str',
                   '    <invoke', '    <invoke',
                   '    </invoke>',
                   '    <invoke>',
                   '    <invoke>',
                   '    <invoke'):
        removed += 1
        continue
    if stripped.startswith('file_path') and '=' not in stripped[:15]:
        removed += 1
        continue
    new_lines.append(line)

print('Removed ' + str(removed) + ' artifact lines')
print('File now has ' + str(len(new_lines)) + ' lines')

with open(r'C:\Users\Usuario\Documents\trae_projects\DJANGO WEB\catalogos\views.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

try:
    import ast
    ast.parse(''.join(new_lines))
    print('SYNTAX OK')
except SyntaxError as e:
    print('SyntaxError at line ' + str(e.lineno) + ': ' + e.msg)
    for k in range(max(0, e.lineno-3), min(len(new_lines), e.lineno+3)):
        print(str(k+1) + ': ' + repr(new_lines[k][:80]))