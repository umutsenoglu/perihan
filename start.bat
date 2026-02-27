@echo off
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
    echo  [1/2] Installing packages...
    "%PYEXE%" -m pip install -r "%~dp0requirements.txt" --no-warn-script-location
    echo  [2/2] Done.
    echo 1 > "%~dp0packages_installed.txt"
    echo.
)

echo  Perihan is running at http://localhost:8765
echo  Close this window to stop.
echo.

start /b cmd /c "timeout /t 3 >nul && start http://localhost:8765"
"%PYEXE%" -m uvicorn main:app --host 0.0.0.0 --port 8765

echo.
echo  Perihan stopped. See any errors above.
pause
