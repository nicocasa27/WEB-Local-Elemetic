"""Configuración para la suite de tests.

La base `mes` sigue siendo PostgreSQL de verdad, no SQLite. Cambiarla por
SQLite haría los tests más cómodos y menos útiles: el código usa
`select_for_update`, `DISTINCT ON`, arrays en SQL crudo y restricciones con
condición, y ninguna de esas cosas se comporta igual en SQLite. Un test que
pasa contra un motor distinto del de producción no prueba lo que dice probar.
"""

import os

from .base import *  # noqa: F401,F403
from .base import DATABASES, env_lista

DEBUG = False

SECRET_KEY = "clave-solo-para-tests-no-se-usa-fuera-de-la-suite"

ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS", "testserver,127.0.0.1,localhost")

DATABASES["mes"]["PASSWORD"] = os.getenv("MES_DB_PASSWORD", "elemetic")
DATABASES["mes"]["HOST"] = os.getenv("MES_DB_HOST", "127.0.0.1")

# Hash rápido: cada test que crea un usuario deja de pagar el coste de PBKDF2.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Los mensajes en memoria evitan depender de sesiones en las pruebas de vistas.
MESSAGE_STORAGE = "django.contrib.messages.storage.fallback.FallbackStorage"

# Que un fallo de plantilla sea un fallo del test y no una cadena vacía.
TEMPLATES[0]["OPTIONS"]["string_if_invalid"] = "«VARIABLE INEXISTENTE: %s»"  # noqa: F405

# Registro silencioso: la suite provoca errores a propósito y no interesa
# verlos en la salida ni acumularlos en logs/.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {"nulo": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["nulo"], "level": "CRITICAL"},
}

# Sin almacenamiento de archivos reales durante los tests.
MEDIA_ROOT = BASE_DIR / "tests" / "_media_tmp"  # noqa: F405
