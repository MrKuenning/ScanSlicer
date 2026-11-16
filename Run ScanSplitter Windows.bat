@echo off
cd /d "%~dp0"

rem If environment is not set up yet, run initial setup launcher
if not exist ".venv\Scripts\pythonw.exe" (
    call "Run ScanSplitter Windows Console.bat"
    exit /b
)

rem Launch ScanSplitter silently using pythonw (no console window)
start "" ".venv\Scripts\pythonw.exe" app\main.py %*
exit
