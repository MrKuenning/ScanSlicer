@echo off
setlocal
cd /d "%~dp0.."

echo ========================================================
echo           ScanSlicer - Windows Executable Builder
echo ========================================================
echo.

rem Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo Please run "Install ScanSplitter Windows.bat" or "Run ScanSplitter Windows Console.bat" first to set up the environment.
    pause
    exit /b 1
)

rem Check if pyinstaller is installed
.venv\Scripts\python.exe -m PyInstaller --version >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Installing PyInstaller in virtual environment...
    call .venv\Scripts\python.exe -m pip install pyinstaller
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

echo [1/3] Cleaning previous build artifacts...
if exist "build" rd /s /q "build"
if exist "releases\ScanSlicer.exe" del /f /q "releases\ScanSlicer.exe"

echo [2/3] Compiling standalone executable with PyInstaller...
echo       - Output: releases\ScanSlicer.exe
echo       - Mode: Standalone single-file (--onefile)
echo       - Window: GUI no-console (--noconsole)
echo       - Icon: assets\icon.ico
echo.

call .venv\Scripts\python.exe -m PyInstaller ^
    --noconsole ^
    --onefile ^
    --clean ^
    --distpath "releases" ^
    --name "ScanSlicer" ^
    --icon "assets\icon.ico" ^
    --add-data "assets;assets" ^
    --hidden-import piexif ^
    app\main.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo ========================================================
    echo [ERROR] Build failed! Check the output logs above.
    echo ========================================================
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================
echo [3/3] Build succeeded!
echo ========================================================
echo Standalone executable created at:
echo   %~dp0ScanSlicer.exe
echo.
echo You can distribute this single file to any Windows PC
echo without needing Python installed.
echo ========================================================
echo.

rem Open the releases folder in Windows File Explorer
explorer "%~dp0"
pause

