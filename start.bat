@echo off
REM Unified MCP Agent Coordinator Startup Script for Windows

setlocal enabledelayedexpansion

REM Default values
set "STDIO_MODE=false"
set "SERVER_HOST=127.0.0.1"
set "SERVER_PORT=8001"

REM Parse command line arguments
:parse_args
if "%~1"=="" goto start_setup
if "%~1"=="--stdio" (
    set "STDIO_MODE=true"
    shift
    goto parse_args
)
if "%~1"=="--host" (
    set "SERVER_HOST=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="--port" (
    set "SERVER_PORT=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="--help" (
    echo Usage: %0 [--stdio] [--host HOST] [--port PORT]
    echo.
    echo Options:
    echo   --stdio          Start in stdio mode for traditional MCP clients
    echo   --host HOST      Set server host (default: 127.0.0.1)
    echo   --port PORT      Set server port (default: 8001)
    echo   --help           Show this help message
    exit /b 0
)
echo Unknown option: %~1
echo Use --help for usage information
exit /b 1

:start_setup
echo ================================
echo MCP Agent Coordinator Server
echo ================================

REM Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment
        echo Make sure Python is installed and accessible from PATH
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo Error: Failed to activate virtual environment
    pause
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo Error: Failed to install dependencies
    pause
    exit /b 1
)

REM Set environment variables and display startup info
if "%STDIO_MODE%"=="true" (
    set "USE_STDIO=true"
    echo.
    echo 🚀 Starting MCP Agent Coordinator in stdio mode
    echo 🔧 Configure in Cursor with stdio transport
    echo 📡 Available tools: 12 coordination tools
    echo Press Ctrl+C to stop the server
) else (
    set "USE_STDIO=false"
    set "MCP_SERVER_HOST=%SERVER_HOST%"
    set "MCP_SERVER_PORT=%SERVER_PORT%"
    echo.
    echo 🚀 Starting MCP Agent Coordinator on http://%SERVER_HOST%:%SERVER_PORT%
    echo 🔧 Use this URL in your Cursor MCP configuration:
    echo    {"mcpServers": {"agent-coordinator": {"url": "http://%SERVER_HOST%:%SERVER_PORT%"}}}
    echo 📡 Available tools: 12 coordination tools
    echo Press Ctrl+C to stop the server
)

echo.

REM Start the server
python main.py
if errorlevel 1 (
    echo.
    echo Server stopped with error
    pause
    exit /b 1
)

echo.
echo Server stopped
pause 