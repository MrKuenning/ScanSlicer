@echo off
setlocal enabledelayedexpansion

rem Set current directory to script location
cd /d "%~dp0"

echo ========================================================
echo               ScanSplitter - Installer
echo ========================================================
echo.

if exist ".venv\Scripts\python.exe" (
    echo Existing virtual environment found ^(.venv^).
    goto :install_deps
)

echo [1/2] Virtual environment not found. Checking for Python installation...

rem Check if python or py launcher is in PATH
set "SYSTEM_PYTHON="
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "SYSTEM_PYTHON=python"
    goto :create_venv
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "SYSTEM_PYTHON=py -3"
    goto :create_venv
)

rem Check common local installation directories
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set "SYSTEM_PYTHON=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    goto :create_venv
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "SYSTEM_PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :create_venv
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "SYSTEM_PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :create_venv
)
if exist "%ProgramFiles%\Python313\python.exe" (
    set "SYSTEM_PYTHON=%ProgramFiles%\Python313\python.exe"
    goto :create_venv
)
if exist "%ProgramFiles%\Python312\python.exe" (
    set "SYSTEM_PYTHON=%ProgramFiles%\Python312\python.exe"
    goto :create_venv
)
if exist "%ProgramFiles%\Python311\python.exe" (
    set "SYSTEM_PYTHON=%ProgramFiles%\Python311\python.exe"
    goto :create_venv
)

rem Python not found - attempt automatic installation via winget
where winget >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================================
    echo  Python was not detected on this PC.
    echo  Installing Python 3.12 automatically via winget...
    echo ========================================================
    echo.
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    echo.

    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "SYSTEM_PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        goto :create_venv
    )
    if exist "%ProgramFiles%\Python312\python.exe" (
        set "SYSTEM_PYTHON=%ProgramFiles%\Python312\python.exe"
        goto :create_venv
    )
    where python >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        set "SYSTEM_PYTHON=python"
        goto :create_venv
    )

    echo [NOTE] Python was installed, but Windows may require opening a new console window
    echo to reload your environment PATH. Please run this script again.
    goto :error
)

echo [ERROR] Python was not found on your system, and winget is not available.
echo Please install Python 3.10+ from: https://www.python.org/downloads/
goto :error

:create_venv
echo Found Python: !SYSTEM_PYTHON!
echo Creating local virtual environment ^(.venv^)...
!SYSTEM_PYTHON! -m venv .venv
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to create virtual environment.
    goto :error
)

:install_deps
echo.
echo [2/2] Installing dependencies from requirements.txt...
call .venv\Scripts\python.exe -m pip install --upgrade pip
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to upgrade pip.
    goto :error
)

call .venv\Scripts\python.exe -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies.
    goto :error
)

echo.
echo ========================================================
echo Installation complete!
echo Run "Run ScanSplitter Windows.bat" to launch the application.
echo ========================================================
echo.
pause
goto :end

:error
echo.
echo ========================================================
echo [ERROR] Installation failed.
echo ========================================================
pause
exit /b 1

:end
exit /b 0
