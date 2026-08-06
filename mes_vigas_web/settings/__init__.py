"""Selector de configuración por entorno.

`DJANGO_SETTINGS_MODULE` sigue apuntando a `mes_vigas_web.settings`, igual
que antes, así que ni manage.py ni wsgi.py ni los .bat de arranque necesitan
cambios. Lo que decide qué se carga encima de `base` es la variable de
entorno `DJANGO_ENV`:

    DJANGO_ENV=prod   -> settings/prod.py   (DEBUG apagado, secretos obligatorios)
    DJANGO_ENV=dev    -> settings/dev.py    (valor por defecto)

El valor por defecto es `dev` a propósito. Poner `prod` por defecto habría
dejado el servidor del taller sin arrancar en cuanto faltara una variable, y
esta configuración se escribió sin acceso a esa máquina. El paso a `prod` es
un cambio deliberado y está descrito paso a paso en DESPLIEGUE.md.
"""
import os
import sys
from pathlib import Path


def _cargar_env():
    """Mete en el entorno lo que diga el archivo `.env`, si lo hay.

    **Esto faltaba, y era un agujero silencioso.** El proyecto traía un
    `.env.example` con todas las variables explicadas, y DESPLIEGUE.md decía
    que se copiara a `.env` y se editara. Pero nada leía ese archivo: la
    configuración llama a `os.getenv` a secas. Quien siguiera las
    instrucciones al pie de la letra escribía ahí la contraseña de PostgreSQL,
    arrancaba, y el sistema intentaba conectarse sin contraseña. El error que
    sale entonces habla de autenticación, no de que el archivo se ignore, así
    que no lleva a ninguna parte.

    Se hace a mano y no con una librería para no añadir una dependencia más
    que instalar en un taller sin internet. Son quince líneas.

    **Lo que ya está en el entorno manda.** Una variable puesta en la ventana
    o en el `.bat` de arranque gana sobre el archivo: si no, no habría forma de
    cambiar algo puntualmente sin editar el archivo, y los tests no podrían
    fijar su propia configuración.
    """
    ruta = Path(__file__).resolve().parent.parent.parent / ".env"
    if not ruta.is_file():
        return
    try:
        contenido = ruta.read_text(encoding="utf-8")
    except OSError:
        return
    for linea in contenido.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        if clave and clave not in os.environ:
            os.environ[clave] = valor


_cargar_env()

ENTORNO = (os.getenv("DJANGO_ENV") or "dev").strip().lower()

from .base import *  # noqa: F401,F403,E402

if ENTORNO in {"prod", "produccion", "production"}:
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403

    # Aviso en consola, no en el log: interesa que lo vea quien arranca el
    # servidor a mano. Se calla durante los tests y los comandos de gestión
    # rutinarios para no ensuciar la salida.
    if "runserver" in sys.argv:
        sys.stderr.write(
            "\n  AVISO: arrancando con la configuración de DESARROLLO "
            "(DEBUG activo, clave de firma insegura).\n"
            "  Para el servidor del taller hay que definir DJANGO_ENV=prod. "
            "Ver DESPLIEGUE.md.\n\n"
        )
