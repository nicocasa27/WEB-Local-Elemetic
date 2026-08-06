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
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY goto :sin_python

%PY% -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 goto :python_viejo

echo  [1/3] Python encontrado
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


:sin_python
echo.
echo  ==================================================================
echo   FALTA PYTHON
echo  ==================================================================
echo.
echo   Python es el programa que hace funcionar el sistema.
echo.
echo   Que hacer:
echo     1. Ir a  https://www.python.org/downloads/windows/
echo     2. Bajar Python 3.12 para Windows, 64 bits
echo     3. Al instalarlo, MARCAR LA CASILLA "Add python.exe to PATH".
echo        Es la de abajo del todo en la primera pantalla. Si no se
echo        marca, esta instalacion no lo va a encontrar.
echo     4. Volver a darle doble clic a INSTALAR.bat
echo.
goto :fin

:python_viejo
echo.
echo  ==================================================================
echo   PYTHON ES DEMASIADO VIEJO
echo  ==================================================================
echo.
%PY% --version
echo.
echo   Hace falta 3.10 o mas nuevo. Instalar Python 3.12 desde
echo   https://www.python.org/downloads/windows/  y marcar la casilla
echo   "Add python.exe to PATH".
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
