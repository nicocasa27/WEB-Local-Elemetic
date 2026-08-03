with open(r'C:\Users\Usuario\Documents\trae_projects\DJANGO WEB\catalogos\views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

with open(r'C:\Users\Usuario\Documents\trae_projects\DJANGO WEB\err_ctx.txt', 'w') as out:
    for k in range(max(0, 2228), min(len(lines), 2245)):
        out.write(str(k+1) + ': (' + str(len(lines[k]) - len(lines[k].lstrip())) + '): ' + repr(lines[k][:80]))