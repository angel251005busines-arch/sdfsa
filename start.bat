@echo off
chcp 65001 >nul
rem ---------------------------------------------------------------------------
rem  Запуск генератора заданий на Windows. Нужен только Python 3.10+.
rem  После запуска откройте в браузере: http://127.0.0.1:8000
rem ---------------------------------------------------------------------------
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo Не найден python. Установите Python 3.10 или новее: https://www.python.org/downloads/
  echo При установке отметьте галочку "Add Python to PATH".
  pause
  exit /b 1
)

python -m boolgen.cli serve --host 127.0.0.1 --port 8000 --pool boolgen_pool.sqlite

echo.
echo Сервер остановлен.
pause
