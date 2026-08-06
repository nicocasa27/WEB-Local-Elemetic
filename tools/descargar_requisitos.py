"""Dejar preparado el instalador de PostgreSQL para una máquina sin internet.

`INSTALAR.bat` lo baja solo la primera vez, y con eso basta si el equipo tiene
internet un rato. Si no lo tiene —que es el caso del taller— hay que traerlo de
fuera, y este guion es para eso: se corre **desde cualquier equipo con
internet**, da igual el sistema operativo, y deja el archivo en su sitio.

    python tools/descargar_requisitos.py

Después se copia la carpeta entera del proyecto al equipo del taller, con la
memoria USB o por la red, y allí `INSTALAR.bat` ya no necesita bajar nada.

Los 350 MB de PostgreSQL **no van en el repositorio** porque GitHub no admite
archivos de más de 100 MB. El de Python, que son 27, sí va, y por eso Python
nunca hace falta bajarlo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requisitos  # noqa: E402


def main():
    print()
    print("Preparando los instaladores para una maquina sin internet")
    print()

    destino = requisitos.INSTALADORES / requisitos.ARCHIVO_POSTGRES
    if destino.exists():
        tamano = destino.stat().st_size / (1024 * 1024)
        print(f"  Ya estaba: {destino.name}  ({tamano:.0f} MB)")
        print("  Para bajarlo otra vez, borrarlo primero.")
        return 0

    print(f"  {requisitos.ARCHIVO_POSTGRES} son unos 350 MB.")
    ok, detalle = requisitos.descargar(requisitos.URL_POSTGRES, destino)
    if not ok:
        print()
        print(f"  NO se pudo: {detalle}")
        print()
        print("  Se puede bajar a mano desde:")
        print(f"    {requisitos.URL_POSTGRES}")
        print(f"  y dejarlo en: {requisitos.INSTALADORES}")
        return 1

    tamano = destino.stat().st_size / (1024 * 1024)
    print()
    print(f"  Listo: {destino.name}  ({tamano:.0f} MB)")
    print()
    print("  Ahora se copia la carpeta entera del proyecto al equipo del")
    print("  taller y alli se le da doble clic a INSTALAR.bat. No va a")
    print("  necesitar internet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
