@echo off
chcp 65001 >nul
title Job Assistant - One-click Setup & Run
cd /d "%~dp0"

echo ================================================
echo   Job Assistant - Xidian Offline Teach-in Crawler
echo   One-click install and run
echo ================================================

REM ---------- Step 0: locate or install Python ----------
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY (
    where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    echo [0/3] Python not found. Trying to install via winget ...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] winget is not available on this system.
        echo         Please install Python 3.10+ manually from:
        echo         https://www.python.org/downloads/
        echo         Remember to check "Add Python to PATH" during installation.
        pause
        exit /b 1
    )
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo [ERROR] Automatic Python install failed.
        echo         Please install Python 3.10+ manually from:
        echo         https://www.python.org/downloads/
        pause
        exit /b 1
    )
    REM refresh PATH to pick up newly installed python
    for /f "tokens=2*" %%A in ('reg query "HKLM\SOFTWARE\Python\PythonCore\3.12\InstallPath" /ve 2^>nul') do set "PYDIR=%%B"
    if not defined PYDIR (
        for /f "tokens=2*" %%A in ('reg query "HKCU\SOFTWARE\Python\PythonCore\3.12\InstallPath" /ve 2^>nul') do set "PYDIR=%%B"
    )
    if defined PYDIR set "PATH=%PYDIR%;%PYDIR%Scripts;%PATH%"
    set "PY=python"
)

echo Python found: %PY%

REM ---------- Step 1: create venv ----------
if not exist ".venv" (
    echo [1/3] Creating virtual environment .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM ---------- Step 2: install dependencies ----------
echo [2/3] Installing dependencies ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Dependency install failed. Check your network and retry.
    pause
    exit /b 1
)

REM ---------- Step 3: run ----------
echo [3/3] Running crawler (next 14 days offline teach-ins) ...
".venv\Scripts\python.exe" main.py

echo.
echo ================================================
echo   Done! Excel output: output\西电线下宣讲会信息汇总.xlsx
echo   Run again with run.bat
echo ================================================
pause
