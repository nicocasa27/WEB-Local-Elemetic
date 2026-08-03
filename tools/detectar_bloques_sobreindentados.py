"""Detecta bloques sobre-indentados respecto a su sentencia de control.

Cuando se borran líneas de en medio de un bloque anidado (que es lo que
hizo cleanup.py con los artefactos de tool-calls), el cuerpo conserva la
indentación profunda pero el `else:`/`if:` que lo encabeza queda a un
nivel más externo. Python lo acepta —la indentación sólo debe ser
consistente dentro del bloque— así que no hay SyntaxError, pero la
semántica cambió: el bloque cuelga de la condición equivocada.

Marcador: el primer statement del cuerpo está a más de 4 espacios de la
sentencia que lo encabeza.
"""
import ast
import sys

SANGRIA = 4


def revisar(ruta):
    src = open(ruta, encoding="utf-8").read()
    lineas = src.split("\n")
    arbol = ast.parse(src)
    hallazgos = []

    for nodo in ast.walk(arbol):
        bloques = []
        if isinstance(nodo, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            bloques.append(("body", nodo.body, nodo.lineno, nodo.col_offset))
            orelse = getattr(nodo, "orelse", None)
            if orelse:
                # el `else:` va justo antes de su primer statement
                ln_else = None
                for k in range(orelse[0].lineno - 2, nodo.lineno - 2, -1):
                    if k < 0:
                        break
                    txt = lineas[k].strip()
                    if txt.startswith(("else:", "elif ")):
                        ln_else = k + 1
                        col_else = len(lineas[k]) - len(lineas[k].lstrip())
                        break
                if ln_else is not None:
                    bloques.append(("orelse", orelse, ln_else, col_else))
            for h in getattr(nodo, "handlers", []) or []:
                bloques.append(("except", h.body, h.lineno, h.col_offset))

        for etiqueta, cuerpo, ln_ctrl, col_ctrl in bloques:
            if not cuerpo:
                continue
            col_cuerpo = cuerpo[0].col_offset
            if col_cuerpo > col_ctrl + SANGRIA:
                hallazgos.append(
                    {
                        "tipo": type(nodo).__name__,
                        "bloque": etiqueta,
                        "linea_control": ln_ctrl,
                        "col_control": col_ctrl,
                        "linea_cuerpo": cuerpo[0].lineno,
                        "col_cuerpo": col_cuerpo,
                        "exceso": col_cuerpo - (col_ctrl + SANGRIA),
                    }
                )
    return sorted(hallazgos, key=lambda h: h["linea_control"])


for ruta in sys.argv[1:]:
    hs = revisar(ruta)
    print(f"\n=== {ruta}: {len(hs)} bloque(s) sobre-indentado(s) ===")
    for h in hs:
        print(
            f"  línea {h['linea_control']:5}  {h['tipo']}.{h['bloque']:<7} "
            f"control col {h['col_control']:2} -> cuerpo col {h['col_cuerpo']:2} "
            f"(+{h['exceso']})   cuerpo en línea {h['linea_cuerpo']}"
        )
