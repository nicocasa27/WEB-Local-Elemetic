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

rem Ya no hace falta fijar MES_DB_HOST aqui: el valor por defecto es 127.0.0.1,
rem que es donde el instalador deja PostgreSQL. Quien la tenga en otra maquina
rem lo pone en .env, y ese archivo manda.

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
