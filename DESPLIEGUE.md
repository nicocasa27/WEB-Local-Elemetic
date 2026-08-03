# Despliegue

## Cómo arranca hoy

El servidor del taller ejecuta `INICIAR_SERVIDOR.bat`, que hace:

```bat
cd /d "C:\Users\Usuario\Documents\trae_projects\DJANGO WEB"
set MES_DB_HOST=127.0.0.1
.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8501
```

Sin `DJANGO_ENV`, eso carga la configuración de **desarrollo**, que es
exactamente el comportamiento que había antes de separar la configuración por
entornos. Nada se rompe por no hacer nada.

Lo que sí conviene es pasar a producción, porque en desarrollo:

- `DEBUG` está activo, así que cualquier error muestra una traza con la
  configuración dentro, **incluida la contraseña de PostgreSQL**;
- la clave de firma de sesiones es pública (está en el repositorio).

## Pasar el servidor a producción

Todo esto se hace **en la máquina del taller**. Conviene hacerlo fuera de
horario y con un respaldo reciente.

### 1. Respaldar

```bat
pg_dump -Fc -h 127.0.0.1 -U postgres mes_vigas -f respaldo_mes_vigas.dump
copy db.sqlite3 db.sqlite3.respaldo
```

Comprobar que el respaldo restaura en una base de prueba antes de seguir.

### 2. Generar la clave de firma

```bat
.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

Guardar el resultado: es el valor de `DJANGO_SECRET_KEY`.

> Cambiar esta clave **cierra todas las sesiones abiertas**. Todo el mundo
> tendrá que volver a iniciar sesión. Por eso conviene hacerlo al final de la
> jornada y avisar antes.

### 3. Crear el archivo `.env`

Copiar `.env.example` a `.env` en la carpeta `DJANGO WEB` y rellenarlo. Como
mínimo `DJANGO_ENV=prod`, `DJANGO_SECRET_KEY` y `MES_DB_PASSWORD`.

`.env` no se versiona. No se sube al repositorio ni se manda por correo.

### 4. Recoger los archivos estáticos

Con `DEBUG` apagado Django ya no sirve el CSS ni el JavaScript por su cuenta;
hay que juntarlos en `STATIC_ROOT`:

```bat
.venv\Scripts\python.exe manage.py collectstatic --noinput
```

Hay que repetirlo después de cada actualización que toque archivos estáticos.

### 5. Actualizar el .bat de arranque

```bat
@echo off
title Servidor Web Taller Elemetic - Django
cd /d "C:\Users\Usuario\Documents\trae_projects\DJANGO WEB"

set DJANGO_ENV=prod
set MES_DB_HOST=127.0.0.1
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
)

.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8501
pause
```

Si el bucle de lectura del `.env` da problemas en esa versión de Windows, la
alternativa es poner los `set` a mano en el `.bat` y proteger el archivo.

### 6. Comprobar

```bat
.venv\Scripts\python.exe manage.py check --deploy
```

Con la configuración de producción quedan seis avisos, todos esperados y
explicados en la sección siguiente. Si aparece `ImproperlyConfigured`, falta
una variable: el mensaje dice cuál.

Después, con el servidor arrancado: entrar, abrir el tablero, abrir un plano
en PDF y registrar un avance.

## Avisos de `check --deploy` que quedan y por qué

| Aviso | Motivo |
|---|---|
| `W004` HSTS | Requiere HTTPS. Se activa solo al poner `DJANGO_HTTPS=1`. |
| `W008` `SECURE_SSL_REDIRECT` | Igual: el taller sirve por HTTP en la red local. Activarlo sin certificado dejaría a todos fuera. |
| `W012` `SESSION_COOKIE_SECURE` | Igual. |
| `W016` `CSRF_COOKIE_SECURE` | Igual. |
| `W009` clave corta | Desaparece al poner una clave generada de verdad. |
| `W019` `X_FRAME_OPTIONS` | Está en `SAMEORIGIN` a propósito: las pantallas de Corta abren contenido propio dentro de un `iframe`. Ponerlo en `DENY` rompería esos modales. |

Los cuatro primeros se cierran de golpe el día que se ponga un proxy con TLS
delante y se defina `DJANGO_HTTPS=1`.

## Archivos subidos

Planos, DXF y comprobantes de envío se sirven por `mes_vigas_web/media_views.py`,
que **exige sesión iniciada**. Antes sólo se servían con `DEBUG` activo (o sea,
dejaban de funcionar en producción) y sin comprobar nada: un acuse de entrega
firmado era accesible para quien acertara la dirección.

## Tarea programada: consolidar los cierres

Cuando una orden llega a su objetivo de piezas queda en «Terminado (bloqueo
pend.)» unos minutos, para poder deshacer un error de dedo. Pasado ese plazo el
cierre debe volverse firme.

Hasta ahora eso sólo ocurría **al abrir la pantalla de control**, así que un
cierre que vencía un viernes a las 17:05 seguía pendiente el lunes por la
mañana, y figuraba como tal en todos los informes.

Hay que programar este comando cada minuto:

```bat
.venv\Scripts\python.exe manage.py consolidar_cierres
```

En Windows, con el Programador de tareas: tarea nueva, repetir cada 1 minuto
indefinidamente, acción «iniciar programa» apuntando al `python.exe` del
entorno virtual, con `manage.py consolidar_cierres` como argumentos y la
carpeta `DJANGO WEB` como directorio de inicio. Conviene marcar «no iniciar una
nueva instancia si ya se está ejecutando».

Para ver qué haría sin tocar nada:

```bat
.venv\Scripts\python.exe manage.py consolidar_cierres --simular
```

El comando no imprime nada cuando no hay trabajo, para no llenar el registro.

Mientras la tarea no esté configurada, la pantalla de control sigue
consolidando los cierres al cargarse, igual que antes: no se rompe nada por
no hacerlo, sólo se mantiene el retraso.

## Registro de actividad

Los registros van a `logs/`, con rotación a los 10 MB y cinco archivos de
histórico:

- `logs/mes.log` — todo lo que llega a nivel INFO o superior.
- `logs/errores.log` — sólo errores y excepciones.

Si algo falla y el usuario no sabe explicar qué, `logs/errores.log` es el
primer sitio donde mirar.

## Volver atrás

La configuración de entorno no toca la base de datos, así que revertir es
quitar `DJANGO_ENV=prod` del `.bat` y reiniciar. Vuelve a arrancar en modo
desarrollo tal como estaba.
