@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Not installed yet. Run install_and_run.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py
pause
