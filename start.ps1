#!/usr/bin/env pwsh
# Unified MCP Agent Coordinator Startup Script

param(
    [switch]$Stdio,
    [string]$ServerHost = "127.0.0.1",
    [int]$Port = 8001
)

Write-Host "================================" -ForegroundColor Cyan
Write-Host "MCP Agent Coordinator Server" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Create virtual environment if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
if ($IsWindows -or $env:OS -eq "Windows_NT") {
    & ".\.venv\Scripts\Activate.ps1"
}
else {
    & "./.venv/bin/activate"
}

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet

# Set environment variables
if ($Stdio) {
    $env:USE_STDIO = "true"
    Write-Host ""
    Write-Host "🚀 Starting MCP Agent Coordinator in stdio mode" -ForegroundColor Green
    Write-Host "🔧 Configure in Cursor with stdio transport" -ForegroundColor Cyan
    Write-Host "📡 Available tools: 12 coordination tools" -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
}
else {
    $env:USE_STDIO = "false"
    $env:MCP_SERVER_HOST = $ServerHost
    $env:MCP_SERVER_PORT = $Port.ToString()
    Write-Host ""
    Write-Host "🚀 Starting MCP Agent Coordinator on http://$ServerHost`:$Port" -ForegroundColor Green
    Write-Host "🔧 Use this URL in your Cursor MCP configuration:" -ForegroundColor Cyan
    Write-Host "   {`"mcpServers`": {`"agent-coordinator`": {`"url`": `"http://$ServerHost`:$Port`"}}}" -ForegroundColor Gray
    Write-Host "📡 Available tools: 12 coordination tools" -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
}

Write-Host ""

try {
    python main.py
}
catch {
    Write-Host "Server stopped" -ForegroundColor Yellow
} 