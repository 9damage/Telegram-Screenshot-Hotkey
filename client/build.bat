@echo off
cd /d "%~dp0"

if not exist config.json (
    echo ERROR: config.json not found.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    pause
    exit /b 1
)

set ICON_ARG=
if exist icon.ico set ICON_ARG=--icon=icon.ico
set VERSION_ARG=
if exist version_info.txt set VERSION_ARG=--version-file=version_info.txt

python -m PyInstaller --noconfirm --clean --onefile --noconsole %ICON_ARG% %VERSION_ARG% --name AvastSvc client.py
if errorlevel 1 (
    pause
    exit /b 1
)

copy /Y config.json dist\config.json >nul

echo.
echo Telegram Screenshot Hotkey v3.0 build complete.
echo dist\AvastSvc.exe
echo dist\config.json
pause
