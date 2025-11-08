#!/bin/bash

echo "Starting BookLister AI..."
echo

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check dependencies
if ! command_exists python3; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

if ! command_exists npm; then
    echo "Error: npm is required but not installed."
    exit 1
fi

# Start Backend
echo "Starting Backend (FastAPI)..."
cd backend
python3 -m pip install -r requirements.txt
python3 main.py &
BACKEND_PID=$!

# Wait for backend to start
echo "Waiting for backend to start..."
sleep 3

# Start Frontend
echo "Starting Frontend (Next.js)..."
cd ../frontend
npm install
npm run dev &
FRONTEND_PID=$!

echo
echo "BookLister AI is starting up!"
echo "Frontend: http://localhost:3001"
echo "Backend API: http://127.0.0.1:8000"
echo "API Docs: http://127.0.0.1:8000/docs"
echo
echo "Press Ctrl+C to stop both servers"

# Function to cleanup background processes
cleanup() {
    echo "Stopping servers..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

# Trap Ctrl+C
trap cleanup INT

# Wait for processes
wait