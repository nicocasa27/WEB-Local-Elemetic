"""Poner PostgreSQL si no está, sin preguntarle nada a nadie.

Lo que el taller pidió es que la instalación no haga preguntas. La única que
quedaba era la contraseña de PostgreSQL, y venía de dos sitios distintos:

- **No está instalado.** Entonces la contraseña no existe todavía, así que la
  inventamos nosotros, se la damos al instalador y la guardamos en `.env`.
  Nadie tiene que saberla ni apuntarla en un papel.
- **Está instalado y la contraseña no la sabe nadie.** Pasa cuando alguien lo
  instaló hace meses. Se restablece sola, y aquí está explicado cómo y por qué
  es seguro hacerlo.

El instalador de PostgreSQL son 350 MB y **no cabe en el repositorio**: el
límite por archivo de GitHub son 100 MB. Así que se baja la primera vez, o se
deja preparado a mano en `vendor/instaladores/` desde una máquina con internet.
Ver `tools/descargar_requisitos.py`.
"""

import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INSTALADORES = RAIZ / "vendor" / "instaladores"

#: La versión que se instala si no hay ninguna. 16 y no la más nueva a
#: propósito: es la que lleva más tiempo en la calle de las que siguen
#: recibiendo parches, y este servidor va a estar años sin que nadie lo toque.
VERSION_POSTGRES = "16.9-1"
ARCHIVO_POSTGRES = f"postgresql-{VERSION_POSTGRES}-windows-x64.exe"
URL_POSTGRES = f"https://get.enterprisedb.com/postgresql/{ARCHIVO_POSTGRES}"

PUERTO_POSTGRES = "5432"


def es_windows():
    return os.name == "nt"


def contrasena_nueva():
    """Una contraseña que nadie tiene que recordar.

    Se guarda en `.env` y la usa sólo el sistema. Sin signos raros a propósito:
    va a viajar por la línea de comandos del instalador de PostgreSQL y por un
    archivo de configuración, y ahí las comillas y los `%` de Windows dan
    problemas que aparecen semanas después.
    """
    alfabeto = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(28))


# ------------------------------------------------------------------ descarga


def descargar(url, destino, avisar=print):
    """Baja un archivo grande enseñando que avanza.

    Se usa `curl.exe`, que viene en Windows 10 y 11 de fábrica, en vez de
    `urllib`: enseña el progreso él solo. Bajar 350 MB sin que la ventana diga
    nada durante diez minutos acaba con alguien cerrándola.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        return False, "no se encontro curl en el sistema"

    avisar(f"   bajando {destino.name} ...")
    resultado = subprocess.run(
        [curl, "-L", "--fail", "--progress-bar", "-o", str(parcial), url]
    )
    if resultado.returncode != 0 or not parcial.exists():
        parcial.unlink(missing_ok=True)
        return False, "no se pudo bajar. Revisar que haya internet en este equipo."

    # Al sitio definitivo sólo cuando terminó. Si no, una descarga cortada a la
    # mitad se queda con el nombre bueno y la siguiente vez se da por hecho que
    # ya está, con un instalador roto que falla sin decir por qué.
    parcial.replace(destino)
    return True, str(destino)


# --------------------------------------------------------------- PostgreSQL


def buscar_psql():
    """Dónde está `psql`. En Windows casi nunca está en el PATH.

    Su instalador no lo añade salvo que alguien marque la casilla, así que
    buscar sólo en el PATH da «no está instalado» en una máquina donde sí lo
    está. Se miran también las rutas donde lo deja por defecto.
    """
    encontrado = shutil.which("psql")
    if encontrado:
        return Path(encontrado)

    candidatos = []
    for base in (r"C:\Program Files\PostgreSQL", r"C:\Program Files (x86)\PostgreSQL"):
        carpeta = Path(base)
        if not carpeta.is_dir():
            continue
        for version in sorted(carpeta.iterdir(), reverse=True):
            candidato = version / "bin" / "psql.exe"
            if candidato.exists():
                candidatos.append(candidato)
    return candidatos[0] if candidatos else None


def probar_conexion(psql, password, host, puerto, usuario):
    entorno = {**os.environ, "PGPASSWORD": password or ""}
    resultado = subprocess.run(
        [str(psql), "-h", host, "-p", str(puerto), "-U", usuario,
         "-d", "postgres", "-tAc", "SELECT 1"],
        capture_output=True, text=True, env=entorno, timeout=30,
    )
    return resultado.returncode == 0, (resultado.stderr or "").strip()


def instalar_postgres(password, avisar=print):
    """Instala PostgreSQL en silencio, con la contraseña que le damos.

    Devuelve `(ok, explicacion)`. Sólo el servidor y las herramientas de línea
    de comandos: ni pgAdmin ni Stack Builder, que son cuatrocientos megas más y
    no los va a abrir nadie en este equipo.
    """
    if not es_windows():
        return False, "solo se puede instalar PostgreSQL desde Windows"

    instalador = INSTALADORES / ARCHIVO_POSTGRES
    if not instalador.exists():
        avisar("   PostgreSQL no esta instalado y no viene en el paquete.")
        avisar("   Son 350 MB: no caben en el repositorio. Se baja una vez.")
        ok, detalle = descargar(URL_POSTGRES, instalador, avisar)
        if not ok:
            return False, detalle

    avisar("   instalando PostgreSQL. Tarda unos minutos, no cerrar...")
    resultado = subprocess.run([
        str(instalador),
        "--mode", "unattended",
        "--unattendedmodeui", "none",
        "--superpassword", password,
        "--serverport", PUERTO_POSTGRES,
        # Sin pgAdmin ni Stack Builder: este equipo es un servidor, no un
        # puesto de trabajo, y son cuatrocientos megas que nadie va a abrir.
        "--disable-components", "pgAdmin,stackbuilder",
    ], capture_output=True, text=True)

    if resultado.returncode != 0:
        return False, (
            "el instalador de PostgreSQL termino con error "
            f"{resultado.returncode}. {(resultado.stderr or '').strip()[:300]}"
        )

    # El servicio tarda un momento en levantar después de instalarse. Sin esta
    # espera, el paso siguiente se encuentra con «no se pudo conectar» y todo
    # parece haber fallado cuando en realidad sólo iba por delante.
    for _ in range(30):
        if buscar_psql():
            time.sleep(2)
            return True, "instalado"
        time.sleep(2)
    return False, "PostgreSQL se instalo pero no se encuentra psql"


# ------------------------------------------- restablecer la contraseña


def _servicio_postgres():
    """El nombre del servicio de Windows, que lleva la version dentro."""
    salida = subprocess.run(
        ["sc", "query", "state=", "all"], capture_output=True, text=True
    ).stdout
    nombres = re.findall(r"SERVICE_NAME:\s*(postgresql[-\w]*)", salida, re.I)
    return nombres[0] if nombres else None


def _carpeta_de_datos(psql):
    """Dónde vive `pg_hba.conf`. Se deduce de dónde está `psql`."""
    candidata = psql.parent.parent / "data"
    return candidata if (candidata / "pg_hba.conf").exists() else None


def restablecer_password(psql, nueva, avisar=print):
    """Le pone una contraseña nueva a `postgres` sin saber la vieja.

    Es el único camino cuando PostgreSQL ya estaba instalado y la contraseña no
    la sabe nadie —lo normal si lo puso otra persona hace meses—, y la
    alternativa es dejar la instalación parada preguntando por un dato que no
    va a aparecer.

    Cómo: PostgreSQL decide si pide contraseña leyendo `pg_hba.conf`. Se le
    cambia esa regla por «desde esta misma máquina, entra sin preguntar», se
    recarga, se cambia la contraseña, **y se deja el archivo como estaba**. La
    ventana en la que se puede entrar sin contraseña dura un par de segundos y
    sólo desde este equipo.

    El archivo original se guarda al lado antes de tocarlo, y se restaura pase
    lo que pase. Dejar una base de datos aceptando conexiones sin contraseña
    porque el instalador se cayó a la mitad sería mucho peor que no haberlo
    intentado.
    """
    if not es_windows():
        return False, "solo desde Windows"

    datos = _carpeta_de_datos(psql)
    if datos is None:
        return False, "no se encontro la configuracion de PostgreSQL"

    servicio = _servicio_postgres()
    if not servicio:
        return False, "no se encontro el servicio de PostgreSQL"

    hba = datos / "pg_hba.conf"
    respaldo = datos / "pg_hba.conf.antes-de-elemetic"
    original = hba.read_text(encoding="utf-8", errors="replace")
    if not respaldo.exists():
        respaldo.write_text(original, encoding="utf-8")

    permisivo = (
        "# Puesto por el instalador del Taller Elemetic para poder cambiar la\n"
        "# contrasena de postgres. Se deja como estaba en cuanto termina.\n"
        "host    all    all    127.0.0.1/32    trust\n"
        "host    all    all    ::1/128         trust\n"
    )

    try:
        hba.write_text(permisivo, encoding="utf-8")
        subprocess.run(["sc", "stop", servicio], capture_output=True, text=True)
        time.sleep(4)
        subprocess.run(["sc", "start", servicio], capture_output=True, text=True)
        time.sleep(6)

        cambio = subprocess.run(
            [str(psql), "-h", "127.0.0.1", "-p", PUERTO_POSTGRES, "-U", "postgres",
             "-d", "postgres", "-c", f"ALTER USER postgres PASSWORD '{nueva}'"],
            capture_output=True, text=True, timeout=60,
        )
        if cambio.returncode != 0:
            return False, (cambio.stderr or "no se pudo cambiar la contrasena").strip()[:300]
        avisar("   contrasena de PostgreSQL restablecida")
        return True, "cambiada"
    finally:
        # Pase lo que pase. Es la parte que no se puede saltar.
        hba.write_text(original, encoding="utf-8")
        subprocess.run(["sc", "stop", servicio], capture_output=True, text=True)
        time.sleep(4)
        subprocess.run(["sc", "start", servicio], capture_output=True, text=True)
        time.sleep(6)
