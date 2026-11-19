@echo off
title PDF Print Router - сборка exe
cd /d "%~dp0"

echo ============================================================
echo  PDF Print Router - автоматическая сборка exe
echo  Ничего предустанавливать не нужно: при отсутствии Python
echo  он будет скачан и установлен для текущего пользователя.
echo ============================================================
echo.

REM --- 1. Ищем Python ---
set "PYDIR=%LOCALAPPDATA%\Programs\Python\Python312"
set "PATH=%PYDIR%;%PYDIR%\Scripts;%PATH%"
python --version >nul 2>nul
if %errorlevel%==0 goto :have_python

echo [1/4] Python не найден. Скачиваю установщик Python 3.12...
curl -L --progress-bar -o "%TEMP%\python-installer.exe" "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
if not exist "%TEMP%\python-installer.exe" (
    echo ОШИБКА: не удалось скачать Python.
    echo Скачайте вручную: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [2/4] Устанавливаю Python (без прав администратора)...
"%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=0
python --version >nul 2>nul
if not %errorlevel%==0 (
    echo ОШИБКА: Python не установился. Установите его вручную
    echo с https://www.python.org/downloads/ и перезапустите этот файл.
    pause
    exit /b 1
)
goto :deps

:have_python
echo [1/4] Python найден:
python --version
echo [2/4] Установка Python не требуется.

:deps
echo [3/4] Устанавливаю зависимости (PySide6, PyMuPDF, pypdf, PyInstaller)...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
if not %errorlevel%==0 (
    echo ОШИБКА при установке зависимостей.
    pause
    exit /b 1
)

echo [4/4] Собираю exe (это займёт несколько минут)...
python -m PyInstaller --noconfirm --clean --windowed --name "PDFPrintRouter" main.py
if not %errorlevel%==0 (
    echo ОШИБКА сборки.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  ГОТОВО! Приложение здесь:
echo  %CD%\dist\PDFPrintRouter\PDFPrintRouter.exe
echo.
echo  Папку dist\PDFPrintRouter можно скопировать куда угодно
echo  и запускать PDFPrintRouter.exe без Python.
echo ============================================================
pause
