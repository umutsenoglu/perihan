#!/bin/bash
echo ""
echo " Starting Perihan..."
echo ""

if ! command -v python3 &>/dev/null; then
    echo " Python 3 not found."
    echo " Please install it from https://python.org"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo " First run - installing dependencies, please wait..."
    echo " This takes a minute only once."
    echo ""
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
    echo " Done."
    echo ""
fi

echo " Perihan is running at http://localhost:8765"
echo " Close this window to stop."
echo ""

(sleep 2 && (xdg-open http://localhost:8765 2>/dev/null || open http://localhost:8765 2>/dev/null)) &

venv/bin/uvicorn main:app --host 0.0.0.0 --port 8765
