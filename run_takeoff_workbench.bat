@echo off
setlocal EnableExtensions
cd /d C:\Tools\takeoff_workbench

if "%TAKEOFF_HOT_RELOAD%"=="" set TAKEOFF_HOT_RELOAD=1
if "%TAKEOFF_RUNTIME_DIR%"=="" set TAKEOFF_RUNTIME_DIR=_runtime

if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
) else if exist "C:\Tools\.venv\Scripts\python.exe" (
    set PYTHON_EXE=C:\Tools\.venv\Scripts\python.exe
) else (
    set PYTHON_EXE=python
)

if not exist "%TAKEOFF_RUNTIME_DIR%" mkdir "%TAKEOFF_RUNTIME_DIR%"

if "%TAKEOFF_HOT_RELOAD%"=="1" (
    "%PYTHON_EXE%" -m takeoff_workbench.dev.hot_relaunch
) else (
    "%PYTHON_EXE%" main.py
)

endlocal
