"""Configuración de desarrollo. Nunca debe usarse en el servidor del taller.

Es el entorno por defecto: sin `DJANGO_ENV=prod` se carga este. La razón está
explicada en settings/__init__.py.
"""

import os

from .base import *  # noqa: F401,F403
from .base import DATABASES, env_lista

DEBUG = True

# Clave de firma fija y pública, sólo para desarrollo. En prod.py se exige que
# venga del entorno.
SECRET_KEY = "django-insecure-solo-para-desarrollo-no-usar-en-el-taller"

ALLOWED_HOSTS = env_lista(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost,0.0.0.0,192.168.50.92,testserver",
)

# En local basta con la contraseña histórica del Postgres de pruebas. En
# producción prod.py la exige por entorno y no acepta valor por defecto.
if not DATABASES["mes"]["PASSWORD"]:
    DATABASES["mes"]["PASSWORD"] = os.getenv("MES_DB_PASSWORD_DEV", "elemetic")

# Sin HTTPS en local: forzar cookies seguras dejaría la sesión inservible.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
