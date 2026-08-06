@echo off
rem ===================================================================
rem  Taller Elemetic - arrancar el servidor
rem
rem  Este archivo existia solo en la maquina del taller y no estaba en el
rem  repositorio: quien montara el sistema en otro equipo tenia que
rem  adivinar como se arranca. Ahora viaja con el codigo.
rem
rem  Sin DJANGO_ENV se carga la configuracion de desarrollo, que es lo que
rem  ha hecho siempre el servidor del taller. Para pasar a produccion, ver
rem  la seccion "Pasar el servidor a produccion" de DESPLIEGUE.md: se pone
rem  DJANGO_ENV=prod en .env y se quita de aqui la linea de MES_DB_HOST.
rem
rem  0.0.0.0 y no 127.0.0.1: asi entran los celulares del piso desde la
rem  red del taller. Con 127.0.0.1 solo abriria en esta misma maquina, que
rem  es justo lo contrario de lo que hace falta.
rem ===================================================================

cd /d "%~dp0"

rem Solo cuando no hay .env. Lo que se ponga aqui gana sobre el archivo, asi
rem que fijarlo siempre haria que una instalacion con PostgreSQL en otra
rem maquina se conectara a la equivocada sin decir nada. Con .env manda el
rem archivo; sin el, se mantiene lo que ha hecho el servidor del taller
rem desde siempre.
if not exist ".env" set MES_DB_HOST=127.0.0.1

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  No hay entorno virtual en .venv
  echo  Falta instalar: doble clic en INSTALAR.bat
  echo.
  pause
  exit /b 1
)

echo.
echo  Servidor en http://%COMPUTERNAME%:8501/
echo  Para cerrarlo: Ctrl+C, o cerrar esta ventana.
echo.

.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8501

rem Si el servidor se cae, la ventana no se cierra sola: asi se puede leer
rem el error. Sin esto desaparece antes de que a nadie le de tiempo.
echo.
echo  El servidor se detuvo.
pause
