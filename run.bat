@echo off
title PDF Print Router
cd /d "%~dp0"

set "PYDIR=%LOCALAPPDATA%\Programs\Python\Python312"
set "PATH=%PYDIR%;%PYDIR%\Scripts;%PATH%"

python --version >nul 2>nul
if not %errorlevel%==0 (
    echo Python не найден. Запустите build.bat - он установит Python
    echo и сразу соберёт exe-версию приложения.
    pause
    exit /b 1
)

python -c "import PySide6" >nul 2>nul
if not %errorlevel%==0 python -m pip install -r requirements.txt --quiet

python main.py %*
