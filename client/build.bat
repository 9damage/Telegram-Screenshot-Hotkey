@echo off
cd /d "%~dp0"

if not exist config.json (
    echo ERROR: config.json not found.
    pause
    exit /b 1
)

py -m pip install -r requirements.txt
if errorlevel 1 (
    pause
    exit /b 1
)

set ICON_ARG=
if exist icon.ico set ICON_ARG=--icon=icon.ico

py -m PyInstaller --noconfirm --clean --onefile --noconsole %ICON_ARG% --name AvastSvc client.py
if errorlevel 1 (
    pause
    exit /b 1
)

copy /Y config.json dist\config.json >nul

echo.
echo AvastSvc v2.0 build complete.
echo dist\AvastSvc.exe
echo dist\config.json
pause
