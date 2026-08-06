"""Dejar el sistema listo para trabajar, sin que quien lo corre sepa nada.

Lo llama `INSTALAR.bat`, que sólo se encarga de encontrar Python y montar el
entorno virtual. Todo lo demás está aquí y no en el `.bat` a propósito: el
lenguaje de los `.bat` no tiene forma decente de comparar versiones, de leer un
archivo de configuración ni de contar lo que salió mal, y cada cosa que se
intenta hacer ahí acaba en una línea de la que nadie se fía. Aquí se puede
probar.

Es **idempotente**. Correrlo dos veces no rompe nada: lo que ya está hecho se
salta y se dice que ya estaba. Eso importa porque el modo de uso real de un
instalador que no se entiende es volver a darle doble clic.

Y **no borra datos nunca**. Si la base ya existe, se usa; si `.env` ya existe,
se respeta lo que hay dentro y sólo se añade lo que falte.
"""

import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PUERTO = 8501

# La consola de Windows no siempre sabe pintar acentos ni la «ñ», y lo que sale
# de `crear_admin` los lleva. Sin esto, un carácter que no cabe en la página de
# códigos tumba el instalador entero con una traza, justo en el paso que le está
# diciendo a alguien cuál es su contraseña.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

#: Lo que hace falta que exista antes de empezar. Se comprueba todo de una vez
#: y se dice todo junto: descubrir los requisitos de uno en uno, cada vez que
#: se vuelve a lanzar, es lo que hace que un instalador se abandone.
VERSION_MINIMA_PYTHON = (3, 10)


# --------------------------------------------------------------- presentación


def paso(texto):
    print(f"\n== {texto}")


def bien(texto):
    print(f"   OK  {texto}")


def aviso(texto):
    print(f"   !   {texto}")


def parar(titulo, explicacion):
    """Se detiene diciendo qué falta y qué hacer. Sin trazas de Python.

    Una traza no le dice nada a quien no programa, y encima da la impresión de
    que el programa está roto cuando lo que pasa es que falta algo por instalar.
    """
    print()
    print("=" * 68)
    print(f"  NO SE PUDO CONTINUAR: {titulo}")
    print("=" * 68)
    print()
    for linea in explicacion.strip().splitlines():
        print(f"  {linea}")
    print()
    sys.exit(1)


# ------------------------------------------------------------- PostgreSQL


def buscar_psql():
    """Dónde está `psql`. En Windows casi nunca está en el PATH.

    El instalador de PostgreSQL no lo añade salvo que alguien marque la casilla,
    así que buscar sólo en el PATH da «no está instalado» en una máquina donde
    sí lo está. Se miran también las rutas donde lo deja por defecto.
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
    entorno = {**os.environ, "PGPASSWORD": password}
    resultado = subprocess.run(
        [str(psql), "-h", host, "-p", str(puerto), "-U", usuario,
         "-d", "postgres", "-tAc", "SELECT 1"],
        capture_output=True, text=True, env=entorno,
    )
    return resultado.returncode == 0, (resultado.stderr or "").strip()


def base_existe(psql, password, host, puerto, usuario, nombre):
    entorno = {**os.environ, "PGPASSWORD": password}
    resultado = subprocess.run(
        [str(psql), "-h", host, "-p", str(puerto), "-U", usuario, "-d", "postgres",
         "-tAc", f"SELECT 1 FROM pg_database WHERE datname='{nombre}'"],
        capture_output=True, text=True, env=entorno,
    )
    return resultado.stdout.strip() == "1"


def crear_base(psql, password, host, puerto, usuario, nombre):
    entorno = {**os.environ, "PGPASSWORD": password}
    resultado = subprocess.run(
        [str(psql), "-h", host, "-p", str(puerto), "-U", usuario, "-d", "postgres",
         "-c", f'CREATE DATABASE "{nombre}"'],
        capture_output=True, text=True, env=entorno,
    )
    if resultado.returncode != 0:
        parar("no se pudo crear la base de datos",
              f"PostgreSQL contesto:\n\n{resultado.stderr.strip()}")


# ----------------------------------------------------------------- el .env


def leer_env(ruta):
    """Lo que ya hay en `.env`, para no pisarlo."""
    valores = {}
    if not ruta.exists():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        valores[clave.strip()] = valor.strip()
    return valores


def escribir_env(ruta, nuevos):
    """Añade o cambia claves conservando lo demás, comentarios incluidos.

    Reescribir el archivo entero perdería las explicaciones de `.env.example`,
    que es donde está dicho qué significa cada variable. En una maquina donde
    nadie programa, ese texto es la unica documentacion que van a leer.
    """
    if ruta.exists():
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    else:
        plantilla = ruta.parent / ".env.example"
        lineas = plantilla.read_text(encoding="utf-8").splitlines() if plantilla.exists() else []

    pendientes = dict(nuevos)
    salida = []
    for linea in lineas:
        limpia = linea.strip()
        if limpia and not limpia.startswith("#") and "=" in limpia:
            clave = limpia.split("=", 1)[0].strip()
            if clave in pendientes:
                salida.append(f"{clave}={pendientes.pop(clave)}")
                continue
        salida.append(linea)

    if pendientes:
        salida.append("")
        salida.append("# Anadido por INSTALAR.bat")
        for clave, valor in pendientes.items():
            salida.append(f"{clave}={valor}")

    ruta.write_text("\n".join(salida) + "\n", encoding="utf-8")


def clave_de_firma():
    """Una clave de sesiones nueva, distinta en cada instalación.

    La del repositorio es publica: cualquiera que vea el codigo puede firmar
    una sesion de administrador. Se genera aqui y se guarda una sola vez;
    cambiarla despues cierra las sesiones abiertas, por eso no se toca si ya
    hay una.
    """
    alfabeto = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alfabeto) for _ in range(64))


# --------------------------------------------------------------- Django


def manage(*argumentos, entorno=None):
    """Corre un comando de Django con el Python del entorno virtual."""
    completo = {**os.environ, **(entorno or {})}
    return subprocess.run(
        [sys.executable, str(RAIZ / "manage.py"), *argumentos],
        cwd=str(RAIZ), env=completo, capture_output=True, text=True,
    )


def correr(descripcion, *argumentos, entorno=None):
    resultado = manage(*argumentos, entorno=entorno)
    if resultado.returncode != 0:
        parar(f"fallo al {descripcion}",
              (resultado.stderr or resultado.stdout or "").strip()[-1500:])
    return resultado


# ----------------------------------------------------------------- Windows


def es_windows():
    return os.name == "nt"


def abrir_el_puerto():
    """Deja entrar a los demas equipos del taller por el puerto del sistema.

    Sin esto el servidor arranca, se abre en la propia maquina, y desde
    cualquier otra no contesta. Es el fallo mas dificil de diagnosticar para
    quien no programa: todo parece bien y nadie puede entrar.
    """
    if not es_windows():
        return "no hace falta fuera de Windows"

    nombre = f"MES Elemetic {PUERTO}"
    consulta = subprocess.run(
        ["netsh", "advfirewall", "firewall", "show", "rule", f"name={nombre}"],
        capture_output=True, text=True,
    )
    if consulta.returncode == 0 and "8501" in consulta.stdout:
        return "ya estaba abierto"

    alta = subprocess.run(
        ["netsh", "advfirewall", "firewall", "add", "rule", f"name={nombre}",
         "dir=in", "action=allow", "protocol=TCP", f"localport={PUERTO}"],
        capture_output=True, text=True,
    )
    if alta.returncode != 0:
        return ("NO se pudo abrir. Hay que correr este instalador como "
                "administrador, o abrir el puerto 8501 a mano en el Firewall "
                "de Windows.")
    return "abierto"


def arrancar_al_encender():
    """Deja el sistema arrancando solo cuando se enciende el equipo.

    Sin esto, el dia que se vaya la luz —o que alguien reinicie— el sistema se
    queda apagado hasta que a alguien se le ocurra ir a darle doble clic. Y
    quien se entera no es quien puede arreglarlo: se entera el piso, cuando ya
    no puede apuntar su trabajo.

    Se usa la carpeta de Inicio y no una tarea programada porque la tarea
    necesita permisos que no siempre estan, y porque un acceso directo lo puede
    borrar cualquiera que decida que ya no lo quiere. Es reversible sin saber
    nada: se abre esa carpeta y se borra.
    """
    if not es_windows():
        return "no hace falta fuera de Windows"

    inicio = Path(os.environ.get("APPDATA", "")) / (
        r"Microsoft\Windows\Start Menu\Programs\Startup")
    if not inicio.is_dir():
        return "no se encontro la carpeta de Inicio de Windows"

    destino = inicio / "Taller Elemetic.lnk"
    if destino.exists():
        return "ya estaba puesto"

    origen = RAIZ / "INICIAR_SERVIDOR.bat"
    guion = (
        "$w = New-Object -ComObject WScript.Shell; "
        f"$s = $w.CreateShortcut('{destino}'); "
        f"$s.TargetPath = '{origen}'; "
        f"$s.WorkingDirectory = '{RAIZ}'; "
        "$s.Description = 'Sistema de produccion del Taller Elemetic'; "
        "$s.Save()"
    )
    hecho = subprocess.run(
        ["powershell", "-NoProfile", "-Command", guion],
        capture_output=True, text=True,
    )
    if hecho.returncode != 0 or not destino.exists():
        return "NO se pudo. Hay que arrancarlo a mano con INICIAR_SERVIDOR.bat"
    return "listo: arranca solo al encender el equipo"


def direcciones_para_entrar():
    """Las direcciones con las que los demas van a entrar desde su equipo."""
    nombre = socket.gethostname()
    direcciones = [f"http://{nombre}:{PUERTO}/"]
    try:
        # Sin enviar nada: solo para que el sistema diga que IP usaria para
        # salir a la red, que es la que ven los demas equipos del taller.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            direcciones.append(f"http://{s.getsockname()[0]}:{PUERTO}/")
    except Exception:
        pass
    direcciones.append(f"http://localhost:{PUERTO}/   (solo en esta maquina)")
    return direcciones


# -------------------------------------------------------------------- guion


def main():
    print()
    print("=" * 68)
    print("  TALLER ELEMETIC - instalacion del sistema de produccion")
    print("=" * 68)

    if sys.version_info < VERSION_MINIMA_PYTHON:
        parar("Python es demasiado viejo",
              f"Hay {sys.version.split()[0]} y hace falta 3.10 o mas nuevo.")

    # --------------------------------------------------------- PostgreSQL
    paso("Buscando PostgreSQL")
    psql = buscar_psql()
    if psql is None:
        parar("PostgreSQL no esta instalado", """
Es la base de datos donde vive todo: las ordenes, las piezas, el almacen.
El sistema no puede funcionar sin ella.

Que hacer:
  1. Instalar PostgreSQL desde https://www.postgresql.org/download/windows/
  2. Durante la instalacion pide una contrasena para el usuario "postgres".
     APUNTARLA: este instalador la va a pedir.
  3. Volver a darle doble clic a INSTALAR.bat
""")
    bien(f"encontrado en {psql}")

    # ------------------------------------------------------------ el .env
    paso("Preparando la configuracion")
    ruta_env = RAIZ / ".env"
    actual = leer_env(ruta_env)

    host = actual.get("MES_DB_HOST") or "127.0.0.1"
    puerto = actual.get("MES_DB_PORT") or "5432"
    usuario = actual.get("MES_DB_USER") or "postgres"
    nombre_base = actual.get("MES_DB_NAME") or "mes_vigas"
    password = actual.get("MES_DB_PASSWORD") or ""

    # Se prueba lo que ya hay antes de preguntar nada, **incluida la
    # contrasena vacia**. Hay instalaciones de PostgreSQL configuradas para
    # dejar entrar sin ella; preguntarsela a alguien que no la tiene porque no
    # existe es mandarlo a buscar un dato que no va a encontrar.
    lista, _ = probar_conexion(psql, password, host, puerto, usuario)
    if lista:
        bien("la conexion guardada en .env sirve")
    elif password:
        aviso("la contrasena guardada en .env ya no sirve")

    intentos = 0
    while not lista:
        intentos += 1
        if intentos > 3:
            parar("no se pudo entrar a PostgreSQL", """
Se agotaron los intentos.

Si no se sabe la contrasena de PostgreSQL, la puede cambiar quien
administre el equipo, o se puede reinstalar PostgreSQL: los datos del
sistema no estan ahi todavia si esta es la primera instalacion.

Volver a darle doble clic a INSTALAR.bat cuando se tenga.
""")
        print()
        print("   Contrasena del usuario 'postgres' de PostgreSQL.")
        print("   Es la que se puso al instalar PostgreSQL, no la de Windows.")
        try:
            intento = input("   Contrasena: ").strip()
        except (EOFError, KeyboardInterrupt):
            # Sin esto, cerrar la ventana escupe una traza de Python que en una
            # maquina donde nadie programa se lee como que el sistema se rompio.
            parar("instalacion cancelada",
                  "No se escribio ninguna contrasena. No se cambio nada.")
        ok, error = probar_conexion(psql, intento, host, puerto, usuario)
        if ok:
            password, lista = intento, True
            bien("conexion correcta")
        else:
            aviso(f"no entro: {error.splitlines()[0] if error else 'sin detalle'}")

    nuevos = {
        "MES_DB_PASSWORD": password,
        "MES_DB_NAME": nombre_base,
        "MES_DB_USER": usuario,
        "MES_DB_HOST": host,
        "MES_DB_PORT": puerto,
    }
    if not actual.get("DJANGO_SECRET_KEY"):
        nuevos["DJANGO_SECRET_KEY"] = clave_de_firma()
        aviso("clave de firma nueva generada: las sesiones abiertas se cierran")
    escribir_env(ruta_env, nuevos)
    bien(f".env listo  (base '{nombre_base}' en {host}:{puerto})")

    entorno = {
        "MES_DB_NAME": nombre_base, "MES_DB_USER": usuario,
        "MES_DB_PASSWORD": password, "MES_DB_HOST": host, "MES_DB_PORT": puerto,
    }

    # ---------------------------------------------------------- la base
    paso("La base de datos")
    if base_existe(psql, password, host, puerto, usuario, nombre_base):
        bien(f"'{nombre_base}' ya existe: se usa tal cual, no se toca nada")
    else:
        crear_base(psql, password, host, puerto, usuario, nombre_base)
        bien(f"'{nombre_base}' creada, vacia")

    # ------------------------------------------------------ migraciones
    paso("Estructura de la base")
    # `default` primero: ahi viven las cuentas y los grupos, y algunas
    # migraciones de negocio los consultan. Al reves falla en una instalacion
    # desde cero con «no such table: auth_group».
    correr("preparar las cuentas", "migrate", "--noinput", entorno=entorno)
    bien("cuentas y sesiones")
    correr("preparar los datos de produccion", "migrate", "--database=mes",
           "--noinput", entorno=entorno)
    bien("ordenes, piezas y almacen")

    # ------------------------------------------------- admin y estaticos
    paso("Administrador y archivos de la pagina")
    salida = correr("crear el administrador", "crear_admin", entorno=entorno)
    bien("administrador listo")
    for linea in salida.stdout.strip().splitlines():
        if "admin" in linea.lower() or "contrase" in linea.lower():
            print(f"       {linea.strip()}")

    correr("preparar los archivos de la pagina", "collectstatic", "--noinput",
           entorno=entorno)
    bien("estilos, iconos y tipografias, servidos desde esta maquina")

    # ------------------------------------------------------------ red
    paso("Permitir que entren los demas equipos")
    print(f"   {abrir_el_puerto()}")

    paso("Arrancar solo al encender el equipo")
    print(f"   {arrancar_al_encender()}")

    # --------------------------------------------------------- resumen
    print()
    print("=" * 68)
    print("  LISTO")
    print("=" * 68)
    print()
    print("  Desde cualquier equipo del taller, entrar con:")
    for direccion in direcciones_para_entrar():
        print(f"      {direccion}")
    print()
    print("  Conviene apuntar la primera y repartirla: es la que van a usar")
    print("  todos, y no cambia aunque cambie la IP de esta maquina.")
    print()
    print("  El sistema arranca solo cada vez que se enciende el equipo.")
    print("  Para arrancarlo ahora sin reiniciar: INICIAR_SERVIDOR.bat")
    print()
    print("  Este instalador se puede volver a correr las veces que haga")
    print("  falta: no borra nada de lo que ya este hecho.")
    print()


if __name__ == "__main__":
    main()
