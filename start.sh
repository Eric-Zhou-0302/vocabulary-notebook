#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Starting backend (uvicorn with auto-reload)..."
source .venv/bin/activate 2>/dev/null || true
uvicorn app:app --host 0.0.0.0 --port 1400 --reload &
BACKEND_PID=$!

echo "Starting frontend (Vite dev server)..."
cd frontend && npm run dev &
FRONTEND_PID=$!

echo ""
echo "Services started:"
echo "  Backend:  http://localhost:1400"
echo "  Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
