@echo off
setlocal EnableExtensions
cd /d C:\Tools\takeoff_workbench

if "%TAKEOFF_COMPANION_HOST%"=="" set TAKEOFF_COMPANION_HOST=127.0.0.1
if "%TAKEOFF_COMPANION_PORT%"=="" set TAKEOFF_COMPANION_PORT=8787

echo.
echo This will expose the local Takeoff Workbench companion through Cloudflare Tunnel.
echo Only use this when remote review is intentional and approved.
echo The companion still requires a token/PIN for write actions.
echo Tunnel target: http://127.0.0.1:%TAKEOFF_COMPANION_PORT%
echo.
pause

start "Takeoff Companion Local" cmd /c run_companion_local.bat

echo Starting Cloudflare Tunnel...
cloudflared tunnel --url http://127.0.0.1:%TAKEOFF_COMPANION_PORT%

endlocal
