#!/usr/bin/env bash
# ============================================================
# VoiceAttend AI – macOS / Linux Quick-Start Script
# ============================================================
# Make executable first:  chmod +x start_backend.sh
# Then run:               ./start_backend.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo ""
echo "================================================"
echo "  VoiceAttend AI – Backend Launcher"
echo "================================================"
echo ""

cd "$BACKEND_DIR"

# Create venv if missing
if [ ! -f "venv/bin/activate" ]; then
    echo "[1/3] Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate
echo "[2/3] Activating virtual environment..."
# shellcheck disable=SC1091
source venv/bin/activate

# Install deps
echo "[3/3] Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
echo "================================================"
echo "  Starting FastAPI on http://0.0.0.0:8000"
echo "  Swagger UI: http://localhost:8000/docs"
echo "  Press Ctrl+C to stop"
echo "================================================"
echo ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
