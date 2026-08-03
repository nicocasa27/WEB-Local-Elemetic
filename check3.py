with open(r'c:\Users\Usuario\Documents\trae_projects\DJANGO WEB\catalogos\views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the end of pedidos_logistica (return render or redirect) - look for the redirect after decote delete
# and then find def pedidos_expediente_zip
pedidos_exp_zip_line = None
for i, l in enumerate(lines):
    if 'def pedidos_expediente_zip' in l:
        pedidos_exp_zip_line = i
        break

print(f'pedidos_expediente_zip found at line {pedidos_exp_zip_line+1}')

# Find the return redirect("catalogos:pedidos_logistica") that ends the POST block
# It should be around line 7106 area
return_line = None
for i in range(pedidos_exp_zip_line - 100, pedidos_exp_zip_line):
    if 'return redirect("catalogos:pedidos_logistica")' in lines[i] and 'decote' not in lines[i]:
        return_line = i
        break

print(f'Last redirect found at line {return_line+1}: {repr(lines[return_line][:60])}')

# Show context around return_line
for i in range(max(0, return_line-2), min(len(lines), return_line+10)):
    print(f'{i+1}: {repr(lines[i])}')