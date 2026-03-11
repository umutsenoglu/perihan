"""Build dist/perihan-install.zip with pre-built wheels.

Contents under perihan/ prefix:
  python/          — embedded Python 3.12 (from dist/python/)
  wheels/          — pre-built .whl files for perihan-core and perihan-app
  start.bat        — Windows launcher
  start.sh         — macOS/Linux launcher
  INSTALL.txt      — instructions
"""

import subprocess
import sys
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parent
DIST = SCRIPT_DIR / "dist"
ZIP_OUT = DIST / "perihan-install.zip"
PREFIX = "perihan"

CORE_DIR = ROOT / "perihan-core"
APP_DIR = ROOT / "perihan-app"
PYTHON_DIR = DIST / "python"
WHEEL_DIR = DIST / "wheels"


def add_tree(zf: zipfile.ZipFile, src: Path, arc_prefix: str, skip_patterns=None):
    """Recursively add a directory tree to the zip."""
    skip = skip_patterns or set()
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        parts = rel.parts
        if any(p in ("__pycache__", ".git") for p in parts):
            continue
        if parts[0] in ("build", "dist"):
            continue
        if any(p.endswith(".egg-info") for p in parts):
            continue
        if any(pat in str(rel) for pat in skip):
            continue
        arc_name = f"{arc_prefix}/{rel.as_posix()}"
        zf.write(path, arc_name)


def build_wheel(pkg_dir: Path, out_dir: Path):
    """Build a wheel for a package and return the .whl path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clean old wheels for this package
    pkg_name = pkg_dir.name
    for old in out_dir.glob(f"{pkg_name.replace('-', '_')}*.whl"):
        old.unlink()

    subprocess.check_call(
        [sys.executable, "-m", "pip", "wheel", str(pkg_dir),
         "--wheel-dir", str(out_dir), "--no-deps"],
        stdout=sys.stdout, stderr=sys.stderr
    )
    wheels = list(out_dir.glob(f"{pkg_name.replace('-', '_')}*.whl"))
    assert len(wheels) == 1, f"Expected 1 wheel for {pkg_name}, found {len(wheels)}"
    return wheels[0]


def main():
    DIST.mkdir(exist_ok=True)

    # Verify prereqs
    assert CORE_DIR.exists(), f"perihan-core/ not found at {CORE_DIR}"
    assert APP_DIR.exists(), f"perihan-app/ not found at {APP_DIR}"
    assert PYTHON_DIR.exists(), f"dist/python/ not found at {PYTHON_DIR}"

    # Build wheels
    print("Building wheels...")
    core_whl = build_wheel(CORE_DIR, WHEEL_DIR)
    print(f"  {core_whl.name}")
    app_whl = build_wheel(APP_DIR, WHEEL_DIR)
    print(f"  {app_whl.name}")

    print(f"Building {ZIP_OUT} ...")

    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Embedded Python runtime
        print("  Adding embedded Python...")
        add_tree(zf, PYTHON_DIR, f"{PREFIX}/python")

        # 2. Wheels
        print("  Adding wheels...")
        zf.write(core_whl, f"{PREFIX}/wheels/{core_whl.name}")
        zf.write(app_whl, f"{PREFIX}/wheels/{app_whl.name}")

        # 3. start.bat
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
    echo  Installing packages...
    "%PYEXE%" -m pip install "%~dp0wheels\perihan_core-0.1.0-py3-none-any.whl" --no-warn-script-location
    if errorlevel 1 (
        echo.
        echo  ERROR: Failed to install core library. Check your internet connection.
        echo.
        pause
        exit /b 1
    )
    "%PYEXE%" -m pip install "%~dp0wheels\perihan_app-0.1.0-py3-none-any.whl" --no-warn-script-location
    if errorlevel 1 (
        echo.
        echo  ERROR: Failed to install app. Check your internet connection.
        echo.
        pause
        exit /b 1
    )
    echo  Done.
    echo 1 > "%~dp0packages_installed.txt"
    echo.
)

REM Verify uvicorn is available before launching
"%PYEXE%" -c "import uvicorn" 2>nul
if errorlevel 1 (
    echo  Dependencies incomplete. Re-installing...
    "%PYEXE%" -m pip install "%~dp0wheels\perihan_core-0.1.0-py3-none-any.whl" --no-warn-script-location
    "%PYEXE%" -m pip install "%~dp0wheels\perihan_app-0.1.0-py3-none-any.whl" --no-warn-script-location
    if errorlevel 1 (
        echo.
        echo  ERROR: Failed to install dependencies.
        echo.
        pause
        exit /b 1
    )
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

        # 4. start.sh
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
    venv/bin/pip install wheels/perihan_core-0.1.0-py3-none-any.whl
    venv/bin/pip install wheels/perihan_app-0.1.0-py3-none-any.whl
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

        # 5. INSTALL.txt
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
  wheels/        Pre-built Python packages
  start.bat      Windows launcher
  start.sh       macOS/Linux launcher

REQUIREMENTS
  - Internet connection on first launch (pip installs dependencies)
  - GEMINI_API_KEY env var OR configure in the UI
  - Optional: Ollama for local LLM models
  - Optional: credentials.json for Google Drive/Gmail
"""
        zf.writestr(f"{PREFIX}/INSTALL.txt", install_txt)

    size_mb = ZIP_OUT.stat().st_size / (1024 * 1024)
    print(f"Done! {ZIP_OUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
