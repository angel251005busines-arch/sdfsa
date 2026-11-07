@echo off
rem ---------------------------------------------------------------------------
rem  boolgen launcher for Windows. Requires Python 3.10 or newer.
rem  ASCII only on purpose: cmd.exe misreads UTF-8 in .bat files.
rem
rem  Usage:  start.bat
rem  Other port: set PORT=9000   then   start.bat
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
title boolgen
chcp 65001 >nul 2>&1

if not defined PORT set "PORT=8000"

set "AUTH="
if "%1"=="--auth" set "AUTH=--auth"

rem --- find Python: py launcher first, then python, then python3 -------------
set "PY="

where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto run

where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto run

where python3 >nul 2>&1
if not errorlevel 1 set "PY=python3"
if not defined PY goto nopython

:run

echo.
echo   boolgen: http://127.0.0.1:%PORT%
echo   Press Ctrl+C to stop.
echo.
%PY% -m boolgen.cli serve --host 127.0.0.1 --port %PORT% --pool boolgen_pool.sqlite %AUTH%
echo.
echo   Server stopped.
pause
exit /b 0

:nopython
echo.
echo   Python 3.10+ was not found.
echo   Install it from https://www.python.org/downloads/
echo   and tick "Add python.exe to PATH" during installation.
echo.
pause
exit /b 1
