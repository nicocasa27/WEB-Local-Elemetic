"""Comprueba que ningún `transaction.atomic` se abre sin indicar la base.

El proyecto usa dos bases: `default` (SQLite, sólo autenticación y sesiones)
y `mes` (PostgreSQL, todos los datos de negocio). `transaction.atomic()` sin
argumento abre la transacción sobre `default`, así que un bloque que escribe
en Postgres queda sin atomicidad ninguna: si falla a la mitad, lo ya escrito
se queda escrito.

Esto afectaba a nueve bloques, cinco de ellos borrados en cascada de DECOTE
que eliminan producción, asignaciones y la orden en tres consultas seguidas.

Se ejecuta desde pre-commit y a mano:

    python3 tools/verificar_atomic.py catalogos/views.py produccion/views.py

Devuelve código de salida 1 si encuentra alguno, para poder encadenarlo en CI.
"""
import ast
import sys


def revisar(ruta):
    arbol = ast.parse(open(ruta, encoding="utf-8").read())
    malos = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        es_atomic = (
            isinstance(f, ast.Attribute)
            and f.attr == "atomic"
            and isinstance(f.value, ast.Name)
            and f.value.id == "transaction"
        )
        if not es_atomic:
            continue
        tiene_using = any(k.arg == "using" for k in nodo.keywords) or bool(nodo.args)
        if not tiene_using:
            malos.append(nodo.lineno)
    return malos


def main(rutas):
    total = 0
    for ruta in rutas:
        malos = revisar(ruta)
        total += len(malos)
        if malos:
            print(f"{ruta}: {len(malos)} transaction.atomic() sin using")
            for ln in malos:
                print(f"    línea {ln}")
        else:
            print(f"{ruta}: correcto")
    if total:
        print(f"\nFALLO: {total} transacción(es) abiertas sobre la base equivocada.")
        print('Usar transaction.atomic(using="mes") para los datos de negocio.')
        return 1
    return 0


if __name__ == "__main__":
    rutas = sys.argv[1:] or ["catalogos/views.py", "produccion/views.py"]
    sys.exit(main(rutas))
