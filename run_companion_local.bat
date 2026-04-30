@echo off
setlocal EnableExtensions
cd /d C:\Tools\takeoff_workbench

if "%TAKEOFF_COMPANION_HOST%"=="" set TAKEOFF_COMPANION_HOST=127.0.0.1
if "%TAKEOFF_COMPANION_PORT%"=="" set TAKEOFF_COMPANION_PORT=8787

if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
) else if exist "C:\Tools\.venv\Scripts\python.exe" (
    set PYTHON_EXE=C:\Tools\.venv\Scripts\python.exe
) else (
    set PYTHON_EXE=python
)

"%PYTHON_EXE%" -m takeoff_workbench.companion.waitress_server

endlocal
