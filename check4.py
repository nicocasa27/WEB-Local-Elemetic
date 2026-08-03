with open(r'c:\Users\Usuario\Documents\trae_projects\DJANGO WEB\catalogos\views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

with open(r'c:\Users\Usuario\Documents\trae_projects\DJANGO WEB\check_output.txt', 'w', encoding='utf-8') as out:
    for i in range(7154, min(7260, len(lines))):
        out.write(f'{i+1}: {repr(lines[i])}')