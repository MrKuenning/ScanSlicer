#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "              ScanSplitter - Installer"
echo "========================================================"
echo

# Locate Python 3.10+
PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[ERROR] Python 3.10 or newer is required but was not found in PATH."
    echo "Please install Python 3.10+ and re-run this script."
    exit 1
fi

echo "Found Python: $($PYTHON_BIN --version)"

if [ ! -x ".venv/bin/python" ]; then
    echo "[1/2] Creating local virtual environment (.venv)..."
    "$PYTHON_BIN" -m venv .venv
else
    echo "[1/2] Existing virtual environment found (.venv)."
fi

echo
echo "[2/2] Installing dependencies from requirements.txt..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo
echo "========================================================"
echo "Installation complete!"
echo "Run the app with: .venv/bin/python app/main.py"
echo "========================================================"
