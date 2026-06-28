@echo off
title AttendanceIQ — Server
color 0A

echo.
echo  =====================================================
echo   AttendanceIQ — Face Recognition Attendance System
echo  =====================================================
echo.

:: ── Check Python is available ────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERROR] Python not found. Please install Python and add it to PATH.
    pause
    exit /b 1
)

:: ── Navigate to the project folder (same folder as this .bat file) ───────────
cd /d "%~dp0"

:: ── Activate virtual environment if it exists ────────────────────────────────
if exist "venv\Scripts\activate.bat" (
    echo  [INFO] Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo  [WARN] No virtual environment found. Using system Python.
    echo  [HINT] Run: python -m venv venv  then  pip install -r requirements.txt
    echo.
)

:: ── Install / verify dependencies silently ───────────────────────────────────
echo  [INFO] Checking dependencies...
pip install -r requirements.txt -q --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo  [ERROR] Failed to install dependencies. Check requirements.txt.
    pause
    exit /b 1
)

:: ── Set environment variables ─────────────────────────────────────────────────
set FLASK_DEBUG=1
set FLASK_ENV=development

:: ── Open browser after a short delay (server needs time to start) ─────────────
echo  [INFO] Starting server on http://localhost:5000 ...
echo  [INFO] Browser will open automatically in 3 seconds.
echo.
echo  Press Ctrl+C in this window to stop the server.
echo  =====================================================
echo.

:: Open browser after 3s delay in background
start "" cmd /c "timeout /t 3 >nul && start http://localhost:5000"

:: ── Start Flask server (keeps window open and shows live logs) ────────────────
python app.py

:: ── If server exits, pause so user can read any error ────────────────────────
echo.
echo  [INFO] Server stopped.
pause
