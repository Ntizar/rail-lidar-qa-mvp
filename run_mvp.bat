@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo === RailLiDAR QA MVP ===
echo Preparando entorno local...
echo.

set PYTHON_CMD=python
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo No se encontro Python. Instala Python 3.12 o superior y vuelve a ejecutar este .bat.
        pause
        exit /b 1
    )
    set PYTHON_CMD=py
)

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual .venv...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo Instalando dependencias Python...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Error instalando dependencias Python.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo No se encontro npm. Instala Node.js para descargar Three.js.
    pause
    exit /b 1
)

if not exist "node_modules\three\build\three.module.js" (
    echo Instalando Three.js...
    npm install
    if errorlevel 1 (
        echo Error instalando dependencias Node.
        pause
        exit /b 1
    )
)

if not exist "web\vendor" mkdir "web\vendor"
copy /Y "node_modules\three\build\three.module.js" "web\vendor\three.module.js" >nul

echo.
echo Arrancando servidor en http://127.0.0.1:8000
echo Cierra esta ventana para parar la aplicacion.
echo.

start "" "http://127.0.0.1:8000"
python src\server.py --host 127.0.0.1 --port 8000

pause
