#!/bin/bash

echo "🚀 Starting Otonom Car Web Version..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "📥 Installing requirements..."
pip install -r requirements.txt

# Check if best.pt exists
if [ ! -f "best.pt" ]; then
    echo "⚠️  Warning: best.pt not found. Please copy your YOLO model to this directory."
    echo "   You can download a sample model: https://github.com/ultralytics/ultralytics"
fi

# Start the web application
echo "🌐 Starting web application..."
echo "📱 Open your browser and go to: http://localhost:8000"
echo "📱 For mobile access: http://[YOUR_IP]:8000"
echo "🛑 Press Ctrl+C to stop"

python web_app.py
