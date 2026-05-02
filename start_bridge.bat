@echo off
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONLEGACYWINDOWSSTDIO=utf-8"

:: Try python3 first (may be from Windows Store), then python
where python3 >nul 2>&1
if %errorlevel% equ 0 (
    python3 main.py >> bridge.log 2>&1
) else (
    python main.py >> bridge.log 2>&1
)