#!/usr/bin/env pwsh
# HTTP MCP Server Startup Script

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Starting HTTP MCP Server" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& ".\.venv\Scripts\Activate.ps1"

# Install uvicorn if not present
Write-Host "Installing/updating dependencies..." -ForegroundColor Yellow
pip install uvicorn --quiet

# Start the HTTP server
Write-Host ""
Write-Host "🚀 Starting MCP Agent Coordinator on http://127.0.0.1:8001" -ForegroundColor Green
Write-Host "🔧 Use this URL in your Cursor MCP configuration:" -ForegroundColor Cyan
Write-Host '   {"mcpServers": {"agent-coordinator": {"url": "http://127.0.0.1:8001"}}}' -ForegroundColor Gray
Write-Host "📡 Available tools: 12 coordination tools" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

try {
    python http_server.py
} catch {
    Write-Host "Server stopped" -ForegroundColor Yellow
} 