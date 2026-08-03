"""Configuración del servidor del taller. Se activa con DJANGO_ENV=prod.

Nada de lo sensible tiene valor por defecto: si falta una variable, el
arranque falla con un mensaje claro en lugar de seguir con un valor inseguro.
Antes ocurría lo contrario: la clave de firma estaba escrita en el código, la
contraseña de PostgreSQL también, y DEBUG valía True salvo que alguien
definiera lo contrario, de modo que un arranque sin variables mostraba
trazas de error con la contraseña de la base dentro.

Los pasos de puesta en marcha están en DESPLIEGUE.md.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import DATABASES, STORAGES, env_bool, env_lista


def requerido(nombre):
    valor = (os.getenv(nombre) or "").strip()
    if not valor:
        raise ImproperlyConfigured(
            f"Falta la variable de entorno {nombre}. "
            f"Es obligatoria con DJANGO_ENV=prod. Ver DESPLIEGUE.md."
        )
    return valor


DEBUG = False

SECRET_KEY = requerido("DJANGO_SECRET_KEY")

ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,192.168.50.92")

DATABASES["mes"]["PASSWORD"] = requerido("MES_DB_PASSWORD")

# Archivos estáticos con hash en el nombre y comprimidos. Exige haber
# ejecutado `collectstatic`; si falta, el arranque avisa en vez de servir la
# aplicación sin estilos y que nadie sepa por qué.
STORAGES["staticfiles"] = {
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}

# Origenes de confianza para CSRF. Con DEBUG apagado y peticiones que no vengan
# de 127.0.0.1, Django los exige para aceptar formularios.
CSRF_TRUSTED_ORIGINS = env_lista(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://192.168.50.92:8501,http://localhost:8501",
)

# HTTPS: hoy el taller sirve por http en la red local, así que activar estas
# banderas dejaría a todo el mundo fuera. Se controlan por variable para poder
# encenderlas el día que haya un proxy con TLS, sin tocar código.
USAR_HTTPS = env_bool("DJANGO_HTTPS", False)
SECURE_SSL_REDIRECT = USAR_HTTPS
SESSION_COOKIE_SECURE = USAR_HTTPS
CSRF_COOKIE_SECURE = USAR_HTTPS
if USAR_HTTPS:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
