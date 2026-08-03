with open(r'c:\Users\Usuario\Documents\trae_projects\DJANGO WEB\catalogos\views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Show lines 7105-7125
for i in range(7104, min(7126, len(lines))):
    print(f'{i+1}: {repr(lines[i])}')