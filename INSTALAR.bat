@echo off
rem ===================================================================
rem  TALLER ELEMETIC - instalar el sistema de produccion
rem
rem  Doble clic y ya. Se puede volver a correr las veces que haga falta:
rem  lo que ya este hecho se salta.
rem
rem  Este archivo hace lo minimo -encontrar Python, montar el entorno e
rem  instalar las librerias- y le pasa el resto a tools\instalar.py. El
rem  lenguaje de los .bat no sabe comparar versiones ni leer un archivo de
rem  configuracion sin retorcerse, y cada cosa que se intenta hacer aqui
rem  acaba en una linea de la que nadie se fia. En Python se puede probar.
rem
rem  Sin acentos a proposito: la consola de Windows los pinta como simbolos
rem  raros salvo que se le cambie la pagina de codigos, y eso trae mas
rem  problemas de los que resuelve.
rem ===================================================================

setlocal
cd /d "%~dp0"
title Taller Elemetic - instalacion

echo.
echo  ==================================================================
echo   TALLER ELEMETIC - instalacion
echo  ==================================================================
echo.

rem --- Administrador -------------------------------------------------
rem Hace falta para abrir el puerto en el Firewall. Sin eso el sistema
rem arranca y funciona en esta maquina, pero desde cualquier otra del
rem taller no contesta, y ese fallo no se parece en nada a su causa.
net session >nul 2>&1
if errorlevel 1 (
  echo  Se necesitan permisos de administrador para abrir el puerto
  echo  en el Firewall de Windows. Va a salir un aviso: darle a SI.
  echo.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

rem --- Python --------------------------------------------------------
call :buscar_python
if defined PY goto :hay_python

rem No esta, o el que hay es demasiado viejo. Se instala solo: el instalador
rem viene en el paquete, asi que no hace falta internet para este paso.
rem
rem PrependPath=1 es lo importante: es la casilla que todo el mundo se salta
rem al instalarlo a mano, y sin ella nada encuentra Python despues.
echo  [1/3] Python no esta. Instalandolo, tarda un par de minutos...
echo.
set "INST_PY=vendor\instaladores\python-3.12.10-amd64.exe"
if not exist "%INST_PY%" goto :sin_instalador_python

"%INST_PY%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_launcher=1
if errorlevel 1 goto :fallo_python

rem El PATH de esta ventana se quedo con el de antes de instalarlo. Se busca
rem tambien donde lo deja el instalador, para no obligar a reiniciar nada.
set "PATH=%PATH%;%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts;%LocalAppData%\Programs\Python\Python312"
call :buscar_python
if not defined PY goto :python_no_aparece
echo.
echo  Python instalado.

:hay_python
echo  [1/3] Python
%PY% --version

rem --- Entorno virtual -----------------------------------------------
if exist ".venv\Scripts\python.exe" (
  echo  [2/3] El entorno ya estaba montado
) else (
  echo  [2/3] Montando el entorno...
  %PY% -m venv .venv
  if errorlevel 1 goto :fallo_venv
)

rem --- Librerias -----------------------------------------------------
rem Desde vendor\ruedas-windows y sin tocar internet: el taller no tiene.
rem Si algun dia se actualiza una version, ver el LEEME de esa carpeta.
rem Sin --quiet a proposito. Tarda medio minuto, y una ventana negra parada
rem sin decir nada se lee como que se colgo: lo siguiente que pasa es que
rem alguien la cierra a la mitad.
echo  [3/3] Instalando librerias. Tarda medio minuto, no cerrar...
echo.
.venv\Scripts\python.exe -m pip install --no-index --disable-pip-version-check ^
  --find-links "vendor\ruedas-windows" -r requirements.txt tzdata
if errorlevel 1 goto :fallo_librerias

rem --- Y el resto, en Python ----------------------------------------
.venv\Scripts\python.exe tools\instalar.py
if errorlevel 1 goto :fin

echo.
echo  Se puede cerrar esta ventana.
goto :fin


rem --- Encontrar un Python que sirva ---------------------------------
rem Deja PY puesto, o vacio si no hay ninguno de 3.10 para arriba. Se prueba
rem el lanzador `py` primero porque elige la version mas nueva instalada.
:buscar_python
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "PY=py -3"
  exit /b
)
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
exit /b


:sin_instalador_python
echo.
echo  ==================================================================
echo   FALTA PYTHON Y NO ESTA SU INSTALADOR
echo  ==================================================================
echo.
echo   Deberia estar en  vendor\instaladores\
echo   Si se descargo el repositorio sin esa carpeta, instalar Python a
echo   mano desde  https://www.python.org/downloads/windows/  MARCANDO
echo   la casilla "Add python.exe to PATH", y volver a intentarlo.
echo.
goto :fin

:fallo_python
echo.
echo   El instalador de Python termino con error. Suele ser que ya hay
echo   una version a medio instalar: desinstalar Python desde Panel de
echo   control y volver a darle doble clic a INSTALAR.bat.
echo.
goto :fin

:python_no_aparece
echo.
echo   Python se instalo pero esta ventana no lo encuentra. Cerrarla y
echo   volver a darle doble clic a INSTALAR.bat: la ventana nueva ya lo
echo   va a ver.
echo.
goto :fin

:fallo_venv
echo.
echo   No se pudo montar el entorno virtual. Suele ser permisos de la
echo   carpeta: probar a mover el sistema a C:\Elemetic y repetir.
echo.
goto :fin

:fallo_librerias
echo.
echo   No se pudieron instalar las librerias.
echo.
echo   Si la carpeta vendor\ruedas-windows esta vacia, el repositorio se
echo   descargo sin ella. Con internet en esta maquina se arregla asi:
echo.
echo     .venv\Scripts\python.exe -m pip install -r requirements.txt tzdata
echo.
goto :fin

:fin
echo.
pause
endlocal
