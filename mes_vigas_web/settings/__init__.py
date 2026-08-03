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
