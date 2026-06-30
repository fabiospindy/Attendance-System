@echo off
setlocal

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo.
echo ========================================
echo   AttendanceIQ Development Launcher
echo   Root: %ROOT%
echo ========================================
echo.

set "VENV_DIR=%ROOT%\venv"
set "REQUIREMENTS=%ROOT%\requirements.txt"
set "APP_ENTRY=%ROOT%\app.py"

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in PATH. Please install Python and ensure it is available.
    pause
    exit /b 1
)

if not exist "%REQUIREMENTS%" (
    echo [ERROR] requirements.txt is missing. Please ensure it exists at the project root.
    pause
    exit /b 1
)

if not exist "%APP_ENTRY%" (
    echo [ERROR] app.py was not found at the project root: %APP_ENTRY%
    pause
    exit /b 1
)

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [WARN] No virtual environment found. Using system Python.
    echo [HINT] Run: python -m venv venv  then  pip install -r requirements.txt
    echo.
)

echo Starting services in their own command windows...
echo.

start "AttendanceIQ Backend" cmd /k "cd /d ""%ROOT%"" && (if exist ""%VENV_DIR%\Scripts\activate.bat"" call ""%VENV_DIR%\Scripts\activate.bat"") && echo [INFO] Checking dependencies... && pip install -r requirements.txt -q --disable-pip-version-check && set FLASK_DEBUG=1 && set FLASK_ENV=development && echo [INFO] Starting Flask server on http://localhost:5000 ... && python app.py"

start "AttendanceIQ Frontend" cmd /k "echo [INFO] Waiting for backend to start... && timeout /t 4 >nul && echo [INFO] Opening http://localhost:5000 in your browser... && start http://localhost:5000 && echo. && echo Frontend is served by the Flask backend at http://localhost:5000 && echo This window can be closed once the page has loaded."

echo.
echo All requested services have been launched.
echo Close each service window individually to stop it.
echo.
pause
endlocal
