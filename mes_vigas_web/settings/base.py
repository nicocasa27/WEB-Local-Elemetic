"""Configuración común a todos los entornos.

Lo que depende del entorno (clave de firma, DEBUG, credenciales de base de
datos, banderas de seguridad) vive en dev.py y prod.py. Aquí sólo va lo que
es igual en los dos.
"""

import os
from pathlib import Path

# settings/ está un nivel más adentro que el antiguo settings.py, de ahí el
# tercer parent: .../DJANGO WEB/mes_vigas_web/settings/base.py -> .../DJANGO WEB
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env_bool(nombre, defecto=False):
    valor = os.getenv(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def env_lista(nombre, defecto=""):
    return [x.strip() for x in os.getenv(nombre, defecto).split(",") if x.strip()]


# ---------------------------------------------------------------- aplicación

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "catalogos",
    "produccion",
    "nucleo",
    "inventario",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "mes_vigas_web.middleware.NoStoreAuthenticatedMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

X_FRAME_OPTIONS = "SAMEORIGIN"

ROOT_URLCONF = "mes_vigas_web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "produccion.context_processors.user_access",
            ],
        },
    },
]

WSGI_APPLICATION = "mes_vigas_web.wsgi.application"


# ------------------------------------------------------------ base de datos
#
# Dos bases: `default` (SQLite) guarda autenticación y sesiones, `mes`
# (PostgreSQL) todos los datos de negocio. El reparto lo hace
# mes_vigas_web.db_router.
#
# La contraseña de `mes` no tiene valor por defecto aquí. dev.py pone uno para
# trabajar en local; prod.py exige que venga del entorno.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
    "mes": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("MES_DB_NAME", "mes_vigas"),
        "USER": os.getenv("MES_DB_USER", "postgres").strip(),
        "PASSWORD": os.getenv("MES_DB_PASSWORD", "").strip(),
        "HOST": os.getenv("MES_DB_HOST", "192.168.50.92"),
        "PORT": int(os.getenv("MES_DB_PORT", "5432")),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"options": "-c lc_messages=C"},
    },
}

DATABASE_ROUTERS = ["mes_vigas_web.db_router.MESRouter"]


# ----------------------------------------------------------------- usuarios

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"


# ------------------------------------------------------------ regionalización

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Merida"
USE_I18N = True
USE_TZ = True


# ----------------------------------------------------------- archivos estáticos

STATIC_URL = "static/"
# Destino de collectstatic. Sin esto, con DEBUG apagado la aplicación se queda
# sin CSS ni JavaScript.
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ------------------------------------------------------------------- negocio

TON_POR_PERSONA_META = float(os.getenv("TON_POR_PERSONA_META", "1.00"))
WEEKLY_SNAPSHOT_RETENTION_WEEKS = int(os.getenv("WEEKLY_SNAPSHOT_RETENTION_WEEKS", "156"))


# ------------------------------------------------------------------ registro
#
# Hasta ahora no había ninguna configuración de logging, de modo que los 163
# bloques `except Exception` del proyecto eran agujeros negros: el error se
# tragaba y no quedaba rastro en ningún sitio.

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detallado": {
            "format": "{asctime} {levelname:8} [{name}] {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "consola": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "archivo": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "mes.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "detallado",
        },
        "archivo_errores": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "errores.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "detallado",
            "level": "ERROR",
        },
    },
    "root": {
        "handlers": ["consola", "archivo"],
        "level": "INFO",
    },
    "loggers": {
        "django.request": {
            "handlers": ["archivo_errores", "consola"],
            "level": "ERROR",
            "propagate": True,
        },
        # Logger propio del proyecto. Es el que usan los except que antes
        # callaban: logging.getLogger("mes.<modulo>").
        "mes": {
            "handlers": ["consola", "archivo", "archivo_errores"],
            "level": "DEBUG",
            "propagate": False,
        },
        # Las consultas SQL sólo cuando se pidan explícitamente.
        "django.db.backends": {
            "handlers": ["consola"],
            "level": os.getenv("DJANGO_SQL_LOG_LEVEL", "WARNING"),
            "propagate": False,
        },
    },
}
