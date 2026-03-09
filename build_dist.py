"""Build dist/perihan-install.zip with the new two-package layout.

Contents under perihan/ prefix:
  python/          — embedded Python 3.12 (from dist/python/)
  perihan-core/    — pip-installable core library
  perihan-app/     — pip-installable FastAPI app
  start.bat        — Windows launcher
  start.sh         — macOS/Linux launcher
  INSTALL.txt      — instructions
"""

import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
ZIP_OUT = DIST / "perihan-install.zip"
PREFIX = "perihan"

# Directories to embed as pip-installable packages
CORE_DIR = ROOT / "perihan-core"
APP_DIR = ROOT / "perihan-app"
PYTHON_DIR = DIST / "python"


def add_tree(zf: zipfile.ZipFile, src: Path, arc_prefix: str, skip_patterns=None):
    """Recursively add a directory tree to the zip."""
    skip = skip_patterns or set()
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        # Skip __pycache__, .egg-info, build artifacts
        parts = rel.parts
        if any(p in ("__pycache__", ".git", "build", "dist") for p in parts):
            continue
        if any(p.endswith(".egg-info") for p in parts):
            continue
        if any(pat in str(rel) for pat in skip):
            continue
        arc_name = f"{arc_prefix}/{rel.as_posix()}"
        zf.write(path, arc_name)


def main():
    DIST.mkdir(exist_ok=True)

    # Verify prereqs
    assert CORE_DIR.exists(), f"perihan-core/ not found at {CORE_DIR}"
    assert APP_DIR.exists(), f"perihan-app/ not found at {APP_DIR}"
    assert PYTHON_DIR.exists(), f"dist/python/ not found at {PYTHON_DIR}"

    print(f"Building {ZIP_OUT} ...")

    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Embedded Python runtime
        print("  Adding embedded Python...")
        add_tree(zf, PYTHON_DIR, f"{PREFIX}/python")

        # 2. perihan-core package
        print("  Adding perihan-core/...")
        add_tree(zf, CORE_DIR, f"{PREFIX}/perihan-core")

        # 3. perihan-app package (includes static/index.html)
        print("  Adding perihan-app/...")
        add_tree(zf, APP_DIR, f"{PREFIX}/perihan-app")

        # 4. start.bat
        print("  Adding start.bat...")
        start_bat = r"""@echo off
echo.
echo  Starting Perihan...
echo.

set PYEXE=%~dp0python\python.exe

if not exist "%PYEXE%" (
    echo  ERROR: Bundled Python runtime not found.
    echo  The installation may be corrupted. Please re-download Perihan.
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0packages_installed.txt" (
    echo  First run - installing dependencies, please wait...
    echo  This takes a few minutes only once.
    echo.
    echo  [1/3] Installing core library...
    "%PYEXE%" -m pip install "%~dp0perihan-core" --no-warn-script-location
    echo  [2/3] Installing app...
    "%PYEXE%" -m pip install "%~dp0perihan-app" --no-warn-script-location
    echo  [3/3] Done.
    echo 1 > "%~dp0packages_installed.txt"
    echo.
)

echo  Perihan is running at http://localhost:8765
echo  Close this window to stop.
echo.

start /b cmd /c "timeout /t 3 >nul && start http://localhost:8765"
"%PYEXE%" -m uvicorn perihan_app.main:app --host 0.0.0.0 --port 8765

echo.
echo  Perihan stopped. See any errors above.
pause
"""
        zf.writestr(f"{PREFIX}/start.bat", start_bat)

        # 5. start.sh
        print("  Adding start.sh...")
        start_sh = r"""#!/bin/bash
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
    venv/bin/pip install ./perihan-core
    venv/bin/pip install ./perihan-app
    echo " Done."
    echo ""
fi

echo " Perihan is running at http://localhost:8765"
echo " Close this window to stop."
echo ""

(sleep 2 && (xdg-open http://localhost:8765 2>/dev/null || open http://localhost:8765 2>/dev/null)) &

venv/bin/uvicorn perihan_app.main:app --host 0.0.0.0 --port 8765
"""
        zf.writestr(f"{PREFIX}/start.sh", start_sh)

        # 6. INSTALL.txt
        print("  Adding INSTALL.txt...")
        install_txt = """Perihan - Document Assistant
============================

QUICK START (Windows)
  1. Extract this zip anywhere
  2. Double-click start.bat
  3. First launch installs dependencies (needs internet, ~200 MB)
  4. Opens http://localhost:8765 automatically

QUICK START (macOS / Linux)
  1. Extract this zip anywhere
  2. Run: chmod +x start.sh && ./start.sh
  3. First launch creates a venv and installs dependencies
  4. Opens http://localhost:8765 automatically

WHAT'S INSIDE
  python/        Embedded Python 3.12 runtime (Windows only)
  perihan-core/  Core library (search, indexing, chat services)
  perihan-app/   FastAPI web application
  start.bat      Windows launcher
  start.sh       macOS/Linux launcher

REQUIREMENTS
  - Internet connection on first launch (pip install)
  - GEMINI_API_KEY env var OR configure in Settings UI
  - Optional: Ollama for local LLM models
  - Optional: credentials.json for Google Drive/Gmail
"""
        zf.writestr(f"{PREFIX}/INSTALL.txt", install_txt)

    size_mb = ZIP_OUT.stat().st_size / (1024 * 1024)
    print(f"Done! {ZIP_OUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
