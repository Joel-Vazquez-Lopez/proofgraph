#!/usr/bin/env bash
set -e

# ==============================================================================
# PayPal AI Dispute Investigator — One-Command Development Launcher
# ==============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "================================================================================"
echo " Starting PayPal AI Dispute Investigator (Hackathon 2026)"
echo " Repository: $ROOT_DIR"
echo "================================================================================"

# Trap SIGINT and SIGTERM to kill background servers on exit
cleanup() {
  echo ""
  echo "Shutting down servers..."
  kill $(jobs -p) 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 1. Start FastAPI Backend
echo "[1/2] Starting FastAPI backend on http://localhost:8000..."
cd "$ROOT_DIR/apps/api"
if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
else
  source .venv/bin/activate
fi

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

# Wait for API to be healthy
echo "Waiting for API to initialize..."
for i in {1..30}; do
  if curl -s http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    echo "✓ Backend API is ready at http://localhost:8000 (Docs: http://localhost:8000/docs)"
    break
  fi
  sleep 0.5
done

# 2. Start Next.js Frontend
echo "[2/2] Starting Next.js frontend on http://localhost:3000..."
cd "$ROOT_DIR/apps/web"
if [ ! -d "node_modules" ]; then
  echo "Installing web dependencies..."
  npm install
fi

npm run dev &
WEB_PID=$!

echo "================================================================================"
echo " All systems operational!"
echo " - Dashboard: http://localhost:3000"
echo " - API Docs:  http://localhost:8000/docs"
echo " Press Ctrl+C to stop both servers."
echo "================================================================================"

wait
