@echo off
REM ============================================================
REM VoiceAttend AI – Windows Quick-Start Script
REM ============================================================
REM Run this from the project root:
REM     .\start_backend.bat
REM ============================================================

echo.
echo ================================================
echo   VoiceAttend AI – Backend Launcher (Windows)
echo ================================================
echo.

REM Navigate to backend folder
cd /d "%~dp0backend"

REM Check if venv exists, create if not
IF NOT EXIST "venv\Scripts\activate.bat" (
    echo [1/3] Creating Python virtual environment...
    python -m venv venv
    IF ERRORLEVEL 1 (
        echo ERROR: Python not found. Install from https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

REM Activate venv
echo [2/3] Activating virtual environment...
call venv\Scripts\activate.bat

REM Install / upgrade dependencies
echo [3/3] Installing dependencies...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo.
echo ================================================
echo   Starting FastAPI server on http://0.0.0.0:8000
echo   Swagger UI: http://localhost:8000/docs
echo   Press Ctrl+C to stop
echo ================================================
echo.

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

pause
