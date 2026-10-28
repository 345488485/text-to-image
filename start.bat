@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-platform.ps1" -Restart
set "result=%errorlevel%"
if not "%result%"=="0" (
    echo.
    echo Startup failed. See the error above.
    pause
)
exit /b %result%
