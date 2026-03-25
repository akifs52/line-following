@echo off
echo 🚀 Starting Otonom Car Web Version...

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python is not installed. Please install Python 3.9 or higher.
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install requirements
echo 📥 Installing requirements...
pip install -r requirements.txt

REM Check if best.pt exists
if not exist "best.pt" (
    echo ⚠️  Warning: best.pt not found. Please copy your YOLO model to this directory.
    echo    You can download a sample model: https://github.com/ultralytics/ultralytics
)

REM Copy best.pt from parent directory if it exists
if exist "..\best.pt" (
    echo 📋 Copying best.pt from parent directory...
    copy "..\best.pt" .
)

REM Start the web application
echo 🌐 Starting web application...
echo 📱 Open your browser and go to: http://localhost:8000
echo 📱 For mobile access: http://[YOUR_IP]:8000
echo 🛑 Press Ctrl+C to stop
echo.

python web_app.py

pause
