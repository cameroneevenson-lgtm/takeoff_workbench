@echo off
cd /d C:\Tools\takeoff_workbench

start "Takeoff Desktop Hot Reload" cmd /c run_takeoff_workbench.bat
start "Takeoff Companion Localhost" cmd /c run_companion_local.bat

echo Desktop and local companion launched.
echo Companion: http://127.0.0.1:8787
echo Cloudflare Tunnel is NOT started by this script.
