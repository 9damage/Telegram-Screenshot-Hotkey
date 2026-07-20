@echo off
cd /d "%~dp0"

if not exist config.json (
    echo ERROR: config.json not found.
    pause
    exit /b 1
)

py -m pip install -r requirements.txt

set ICON_ARG=
if exist icon.ico set ICON_ARG=--icon=icon.ico

py -m PyInstaller --noconfirm --clean --onefile --console %ICON_ARG% --name AvastSvc_DEBUG client.py
copy /Y config.json dist\config.json >nul
pause
