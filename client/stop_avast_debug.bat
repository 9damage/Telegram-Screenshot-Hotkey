@echo off
setlocal EnableExtensions

fltmc >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo Processes before:
tasklist | findstr /I "AvastSvc"

echo.
echo Killing AvastSvc.exe...
taskkill /F /T /IM AvastSvc.exe

echo.
echo Processes after:
tasklist | findstr /I "AvastSvc"

echo.
pause
