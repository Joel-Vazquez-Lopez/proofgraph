#!/bin/sh
set -eu

export DATABASE_URL="${DATABASE_URL:-sqlite:////tmp/proofgraph-demo.db}"
export UPLOAD_DIR="${UPLOAD_DIR:-/tmp/proofgraph-uploads}"
export DEMO_MODE=true
export PUBLIC_READ_ONLY=true
export PAYPAL_ENVIRONMENT=sandbox

mkdir -p "$UPLOAD_DIR"

cd /app

/opt/proofgraph-venv/bin/uvicorn app.main:app --app-dir /app/apps/api --host 127.0.0.1 --port 8000 &
API_PID=$!

cd /app/apps/web
./node_modules/.bin/next start -H 0.0.0.0 -p 7860 &
WEB_PID=$!

trap 'kill "$API_PID" "$WEB_PID" 2>/dev/null || true' INT TERM

wait "$WEB_PID"
