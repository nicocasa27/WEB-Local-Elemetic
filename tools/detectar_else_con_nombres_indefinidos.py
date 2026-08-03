"""Detecta bloques `else:` colgados del `if` equivocado.

Patrón buscado: un `if` cuyo `orelse` usa nombres que sólo se asignan
dentro de su propio `body`. Si el `else` realmente perteneciera a ese
`if`, esos nombres nunca estarían definidos al ejecutarlo, así que la
rama o revienta con NameError o es inalcanzable. Es la firma que dejó
la corrupción por artefactos de tool-calls documentada en cleanup.py.
"""
import ast
import sys


def nombres_asignados(nodos):
    out = set()
    for n in nodos:
        for sub in ast.walk(n):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                out.add(sub.id)
            elif isinstance(sub, (ast.Import, ast.ImportFrom)):
                for a in sub.names:
                    out.add((a.asname or a.name).split(".")[0])
            elif isinstance(sub, ast.withitem) and isinstance(sub.optional_vars, ast.Name):
                out.add(sub.optional_vars.id)
    return out


def nombres_leidos(nodos):
    out = set()
    for n in nodos:
        for sub in ast.walk(n):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                out.add(sub.id)
    return out


def analizar(ruta):
    src = open(ruta, encoding="utf-8").read()
    arbol = ast.parse(src)
    hallazgos = []

    for fn in ast.walk(arbol):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # nombres visibles fuera de cualquier `if` de esta función:
        # parámetros y asignaciones en el cuerpo de nivel superior
        params = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
        if fn.args.vararg:
            params.add(fn.args.vararg.arg)
        if fn.args.kwarg:
            params.add(fn.args.kwarg.arg)

        for nodo in ast.walk(fn):
            if not isinstance(nodo, ast.If) or not nodo.orelse:
                continue
            # `elif` encadenado: el orelse es otro If en la misma línea lógica
            asignados_en_body = nombres_asignados(nodo.body)
            leidos_en_else = nombres_leidos(nodo.orelse)
            sospechosos = asignados_en_body & leidos_en_else
            if not sospechosos:
                continue
            # descartar los que también se definen antes del if, en la función
            definidos_fuera = params | nombres_asignados(
                [s for s in fn.body if s is not nodo]
            )
            reales = sospechosos - definidos_fuera
            if reales:
                hallazgos.append(
                    {
                        "funcion": fn.name,
                        "linea_if": nodo.lineno,
                        "linea_else": nodo.orelse[0].lineno,
                        "nombres": sorted(reales),
                    }
                )
    return hallazgos


for ruta in sys.argv[1:]:
    hs = analizar(ruta)
    print(f"\n=== {ruta}: {len(hs)} hallazgo(s) ===")
    for h in hs:
        print(
            f"  {h['funcion']:38} if línea {h['linea_if']:5}  "
            f"else línea {h['linea_else']:5}  nombres: {', '.join(h['nombres'])}"
        )
