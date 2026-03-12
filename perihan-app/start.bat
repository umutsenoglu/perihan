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

if not exist "%~dp0packages_installed.txt" call :do_install
if errorlevel 1 exit /b 1

echo  Perihan is running at http://localhost:8765
echo  Close this window to stop.
echo.

start /b cmd /c "timeout /t 3 >nul && start http://localhost:8765"
"%PYEXE%" -m uvicorn main:app --host 0.0.0.0 --port 8765

echo.
echo  Perihan stopped. See any errors above.
pause
exit /b 0

:do_install
echo  First run - installing dependencies, please wait...
echo  This only happens once.
echo.

echo  Step 1 of 4: Installing web framework...
"%PYEXE%" -m pip install fastapi uvicorn httptools httpx --no-warn-script-location --progress-bar on -q
if errorlevel 1 goto :install_error
echo              Done.
echo.

echo  Step 2 of 4: Installing document readers...
"%PYEXE%" -m pip install python-docx PyPDF2 --no-warn-script-location --progress-bar on -q
if errorlevel 1 goto :install_error
echo              Done.
echo.

echo  Step 3 of 4: Installing Google services...
"%PYEXE%" -m pip install google-auth google-auth-oauthlib google-api-python-client --no-warn-script-location --progress-bar on -q
if errorlevel 1 goto :install_error
echo              Done.
echo.

echo  Step 4 of 4: Installing AI and search engine (this is the big one, please wait)...
"%PYEXE%" -m pip install openai chromadb --no-warn-script-location --progress-bar on
if errorlevel 1 goto :install_error
echo              Done.
echo.

echo 1 > "%~dp0packages_installed.txt"
echo  All dependencies installed successfully!
echo.
exit /b 0

:install_error
echo.
echo  ERROR: Installation failed. Please check your internet connection and try again.
echo.
pause
exit /b 1
