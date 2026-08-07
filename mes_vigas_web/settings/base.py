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


def nombres_de_esta_maquina():
    """Cómo se puede llamar a este equipo desde la red del taller.

    Django rechaza con **400** cualquier petición cuyo `Host:` no esté en
    `ALLOWED_HOSTS`. Hasta ahora la lista traía escrita a mano la IP del
    servidor del taller, `192.168.50.92`, y eso rompía dos casos que son
    justamente los normales:

    - Se instala en otro equipo. La IP es otra, así que desde cualquier
      computadora de la red sale «Bad Request (400)». Desde el propio servidor
      abre bien, porque ahí se entra por `localhost`. El fallo se ve como «no
      me abre desde las demás», que es exactamente como se ve un problema de
      firewall, y por ahí se va a buscar.
    - Se entra por el nombre del equipo, que es lo que aconseja repartir el
      LEEME porque no cambia cuando cambia la IP. El nombre tampoco estaba en
      la lista, así que la dirección que el propio sistema anuncia al terminar
      de instalarse no funcionaba.

    Se resuelve preguntándole a la máquina cómo se llama en vez de suponerlo:
    el nombre corto, el largo y todas sus IPv4. `DJANGO_ALLOWED_HOSTS` sigue
    mandando cuando está puesta, para el día que haya un nombre de dominio o un
    proxy delante.

    Si la resolución de nombres falla -pasa con la red del taller caída- se
    devuelve lo que se haya podido averiguar y no se rompe el arranque: un
    servidor que no levanta es peor que uno al que le falta un alias.
    """
    import socket

    nombres = set()
    try:
        corto = socket.gethostname()
    except OSError:
        return []

    # Todo en minúsculas. Django compara el `Host:` de la petición ya pasado a
    # minúsculas contra los patrones **tal cual están escritos**, así que un
    # patrón con mayúsculas no casa nunca. Y en Windows el nombre del equipo
    # suele venir en mayúsculas -SERVIDOR-TALLER-, o sea que sin esto el nombre
    # de la máquina seguiría dando 400 justo en el sistema donde corre.
    nombres.add(corto.lower())
    try:
        nombres.add(socket.getfqdn(corto).lower())
    except OSError:
        pass

    try:
        for datos in socket.getaddrinfo(corto, None, socket.AF_INET):
            nombres.add(datos[4][0])
    except OSError:
        pass

    # `getaddrinfo` sobre el propio nombre no siempre devuelve la IP con la que
    # se sale a la red: en un equipo con cable y wifi a la vez puede dar sólo
    # una, y el taller entra por la otra. Este truco la consigue sin depender
    # de la tabla de nombres: se prepara un socket UDP hacia fuera -no llega a
    # enviar nada, UDP no abre conexión- y se le pregunta por qué interfaz
    # habría salido.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.2)
            s.connect(("8.8.8.8", 80))
            nombres.add(s.getsockname()[0])
    except OSError:
        pass

    # `getfqdn` a veces devuelve el nombre inverso de la IP local
    # -«1.0.0.127.in-addr.arpa»-, que no es un nombre por el que nadie vaya a
    # entrar y sólo ensucia la lista.
    return sorted(n for n in nombres if n and not n.endswith(".in-addr.arpa"))


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
    "costeo",
    # Recursos humanos: departamentos, puestos y la ficha de cada persona.
    "personal",
    # Entrar con cuatro dígitos desde la tableta del piso. Va en la base
    # `default`, junto a `auth`, porque apunta a `User` con una clave foránea.
    "acceso",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Sirve los archivos estáticos desde el propio Django. Va inmediatamente
    # después del middleware de seguridad, como pide whitenoise.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "mes_vigas_web.middleware.NoStoreAuthenticatedMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Cierra sola la sesión de la tableta del piso tras un rato sin usarse.
    # Va después de la de mensajes porque avisa con un mensaje.
    "acceso.middleware.CierreDePinPorInactividad",
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
                "produccion.context_processors.navegacion",
            ],
        },
    },
]

WSGI_APPLICATION = "mes_vigas_web.wsgi.application"


# ------------------------------------------------------------ base de datos
#
# Hay dos formas, y se elige con `MES_UNA_SOLA_BASE`.
#
# **Como está hoy (por defecto).** Dos bases: `default` (SQLite) guarda
# autenticación y sesiones, `mes` (PostgreSQL) todos los datos de negocio. El
# reparto lo hace mes_vigas_web.db_router. Eso no responde a ninguna decisión
# de diseño: es lo que deja `startproject` y nadie lo cambió. Cuesta caro —
# ningún registro puede apuntar con una clave foránea a quien lo hizo, así que
# la identidad se guarda como texto en 28 campos de 22 modelos.
#
# **Con `MES_UNA_SOLA_BASE=1`.** Una sola base PostgreSQL, con las tablas del
# negocio en un esquema propio. El alias por el que se escribe lo dice
# `MES_DB_ALIAS` más abajo, y el código lo lee de `core.bases.BASE`: nadie
# escribe el nombre a mano.
#
# La contraseña no tiene valor por defecto aquí. dev.py pone uno para trabajar
# en local; prod.py exige que venga del entorno.

UNA_SOLA_BASE = env_bool("MES_UNA_SOLA_BASE", False)

#: El esquema donde viven las tablas del negocio cuando hay una sola base.
#: Un esquema por ERP es lo que permite meter Producción, RRHH y Ventas en la
#: misma base de Supabase sin que puedan verse entre ellos.
MES_DB_ESQUEMA = os.getenv("MES_DB_ESQUEMA", "produccion").strip()


def _postgres(esquema=""):
    opciones = ["-c lc_messages=C"]
    if esquema:
        # Django no sabe de esquemas y no le hace falta: crea las tablas en el
        # primero del `search_path`. `public` se queda detrás porque ahí viven
        # las extensiones.
        opciones.append(f"-c search_path={esquema},public")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("MES_DB_NAME", "mes_vigas"),
        "USER": os.getenv("MES_DB_USER", "postgres").strip(),
        "PASSWORD": os.getenv("MES_DB_PASSWORD", "").strip(),
        # 127.0.0.1, no la IP del servidor del taller. El instalador pone
        # PostgreSQL en la misma máquina, así que ese es el caso normal. Con la
        # IP del taller como valor por defecto, una instalación nueva se
        # intentaba conectar a la base de OTRA máquina -o se quedaba esperando
        # hasta agotar el tiempo, si esa máquina no estaba en la red- y el
        # error no mencionaba en ningún sitio de dónde salía esa dirección.
        # Quien tenga la base en otro equipo lo pone en `.env`.
        "HOST": os.getenv("MES_DB_HOST", "127.0.0.1"),
        "PORT": int(os.getenv("MES_DB_PORT", "5432")),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"options": " ".join(opciones)},
    }


if UNA_SOLA_BASE:
    DATABASES = {
        "default": _postgres(MES_DB_ESQUEMA),
        "mes": _postgres(MES_DB_ESQUEMA),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        },
        "mes": _postgres(),
    }

DATABASE_ROUTERS = ["mes_vigas_web.db_router.MESRouter"]

#: El alias por el que se escribe el negocio. **Se usa siempre a través de
#: `core.bases.BASE`**, nunca escrito a mano.
#:
#: Existe porque el alias no puede quedarse fijo en `"mes"`. Django abre **una
#: conexión por alias**, así que con una sola base dos alias son dos
#: transacciones contra el mismo PostgreSQL: lo que escribe una no lo ve la
#: otra, y `transaction.atomic(using="mes")` dejaría de cubrir lo que se
#: escribe por `default`. Eso no falla ruidosamente; sólo deja los datos a
#: medias de vez en cuando.
#:
#: Y al revés tampoco vale dejarlo en `"default"` mientras haya dos bases: sería
#: abrir la transacción sobre SQLite mientras se escribe en PostgreSQL, que es
#: la «atomicidad falsa» que este proyecto ya arregló una vez.
#:
#: Por eso lo decide la configuración, y cambiar de base es **un solo
#: movimiento** en vez de una migración a medias.
MES_DB_ALIAS = "default" if UNA_SOLA_BASE else "mes"


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

# «es» a secas es el español de España, que escribe 1 234,56: coma decimal y
# espacio fino para los miles. Aquí se escribe 1,234.56. La diferencia no es
# cosmética: un peso de «1,600» kg se leía como mil seiscientos.
LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Merida"
USE_I18N = True
USE_TZ = True


# ----------------------------------------------------------- archivos estáticos

STATIC_URL = "static/"
# Destino de collectstatic. Sin esto, con DEBUG apagado la aplicación se queda
# sin CSS ni JavaScript.
STATIC_ROOT = BASE_DIR / "staticfiles"

# Bootstrap, los iconos, Chart.js y el generador de códigos QR viven en
# `produccion/static/vendor/` y están versionados en git. Antes venían de un
# CDN: sin internet el taller veía la aplicación sin estilos y sin JavaScript,
# es decir, no podía trabajar. No hay proceso de compilación ni npm a
# propósito: en un equipo sin Node, añadirlo es añadir algo que nadie va a
# mantener.
# En prod.py se cambia por la variante con hash en el nombre. Aquí no, porque
# ésa exige haber ejecutado collectstatic y dejaría el servidor de desarrollo
# sin arrancar hasta hacerlo.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

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
