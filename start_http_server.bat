@echo off
REM HTTP MCP Server Startup Script

echo ================================
echo Starting HTTP MCP Server
echo ================================

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Install uvicorn if not present
echo Installing/updating dependencies...
pip install uvicorn --quiet

REM Start the HTTP server
echo.
echo Starting MCP Agent Coordinator on http://127.0.0.1:8001
echo Use this URL in your Cursor MCP configuration
echo Press Ctrl+C to stop the server
echo.

python http_server.py

pause 