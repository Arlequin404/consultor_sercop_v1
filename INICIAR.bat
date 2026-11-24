@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run
where py >nul 2>&1
if not errorlevel 1 (
 py -3 -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
 if not errorlevel 1 goto create_py
)
where python >nul 2>&1
if errorlevel 1 goto no_python
python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if errorlevel 1 goto no_python
echo Creando entorno virtual...
python -m venv .venv
if errorlevel 1 goto venv_error
goto run
:create_py
echo Creando entorno virtual...
py -3 -m venv .venv
if errorlevel 1 goto venv_error
:run
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto run_error
exit /b 0
:no_python
echo Se necesita Python 3.10 o superior instalado y disponible en PATH.
pause
exit /b 1
:venv_error
echo No se pudo crear el entorno virtual. Comprueba Python y los permisos.
pause
exit /b 1
:run_error
echo La aplicacion termino con un error. Revisa el mensaje anterior.
pause
exit /b 1
