@echo off
REM MCP Agent Coordinator - Windows Batch Startup Script
REM This script sets up the environment and starts the MCP server

echo ================================
echo MCP Agent Coordinator Setup
echo ================================

REM Check if Python is installed
echo.
echo Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    echo Make sure to check 'Add Python to PATH' during installation
    pause
    exit /b 1
)

REM Get Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Python found: Python %PYTHON_VERSION%

REM Note: Batch files can't easily check Python version, so we'll proceed
echo Note: This script requires Python 3.8 or higher

REM Set up virtual environment
set VENV_PATH=.venv
if exist "%VENV_PATH%" (
    echo.
    echo Virtual environment already exists
) else (
    echo.
    echo Creating virtual environment...
    python -m venv %VENV_PATH%
    if %errorlevel% neq 0 (
        echo Error: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created
)

REM Activate virtual environment
echo.
echo Activating virtual environment...
call %VENV_PATH%\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo Error: Failed to activate virtual environment
    pause
    exit /b 1
)
echo Virtual environment activated

REM Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1
echo Pip upgraded

REM Install MCP SDK
echo.
echo Installing MCP SDK...
pip list | findstr /B /C:"mcp " >nul 2>&1
if %errorlevel% equ 0 (
    echo MCP SDK already installed
    goto :continue_after_mcp_install
)

echo Installing MCP SDK...
pip install mcp
if %errorlevel% equ 0 (
    echo MCP SDK installed
    goto :continue_after_mcp_install
)

echo Error: Failed to install MCP SDK
echo Trying alternative installation method...
pip install "mcp @ git+https://github.com/modelcontextprotocol/python-sdk.git"
if %errorlevel% equ 0 (
    echo MCP SDK installed (via git URL)
    goto :continue_after_mcp_install
)

echo Error: Could not install MCP SDK
pause
exit /b 1

:continue_after_mcp_install

REM Check if database exists
if exist "db.sqlite" (
    echo.
    echo Database already exists
) else (
    echo.
    echo Warning: Database not found at db.sqlite
    echo Make sure the database schema has been created
)

REM Start the MCP server
echo.
echo ================================
echo Starting MCP Agent Coordinator
echo ================================
echo Press Ctrl+C to stop the server
echo.

REM Set environment variable for unbuffered output
set PYTHONUNBUFFERED=1

REM Run the server
python server.py

REM Deactivate virtual environment on exit
call deactivate >nul 2>&1
pause 