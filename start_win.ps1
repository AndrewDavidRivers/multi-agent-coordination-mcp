#!/usr/bin/env pwsh
# MCP Agent Coordinator - Windows Startup Script
# This script sets up the environment and starts the MCP server

Write-Host "================================" -ForegroundColor Cyan
Write-Host "MCP Agent Coordinator Setup" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Check if Python is installed
Write-Host "`nChecking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python (\d+)\.(\d+)") {
        $majorVersion = [int]$matches[1]
        $minorVersion = [int]$matches[2]
        if ($majorVersion -lt 3 -or ($majorVersion -eq 3 -and $minorVersion -lt 8)) {
            Write-Host "Error: Python 3.8 or higher is required. Found: $pythonVersion" -ForegroundColor Red
            Write-Host "Please install Python 3.8+ from https://www.python.org/downloads/" -ForegroundColor Yellow
            exit 1
        }
        Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
    }
} catch {
    Write-Host "Error: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.8+ from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add Python to PATH' during installation" -ForegroundColor Yellow
    exit 1
}

# Set up virtual environment
$venvPath = ".\.venv"
if (Test-Path $venvPath) {
    Write-Host "`n✓ Virtual environment already exists" -ForegroundColor Green
} else {
    Write-Host "`nCreating virtual environment..." -ForegroundColor Yellow
    python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Virtual environment created" -ForegroundColor Green
}

# Activate virtual environment
Write-Host "`nActivating virtual environment..." -ForegroundColor Yellow
$activateScript = "$venvPath\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    & $activateScript
    Write-Host "✓ Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "Error: Could not find activation script" -ForegroundColor Red
    exit 1
}

# Upgrade pip
Write-Host "`nUpgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip --quiet
Write-Host "✓ Pip upgraded" -ForegroundColor Green

# Install MCP SDK
Write-Host "`nInstalling MCP SDK..." -ForegroundColor Yellow
$mcpInstalled = pip list 2>&1 | Select-String -Pattern "^mcp\s+"
if ($mcpInstalled) {
    Write-Host "✓ MCP SDK already installed" -ForegroundColor Green
} else {
    pip install mcp
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to install MCP SDK" -ForegroundColor Red
        Write-Host "Trying alternative installation method..." -ForegroundColor Yellow
        pip install "mcp @ git+https://github.com/modelcontextprotocol/python-sdk.git"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: Could not install MCP SDK" -ForegroundColor Red
            exit 1
        }
    }
    Write-Host "✓ MCP SDK installed" -ForegroundColor Green
}

# Check if database exists
$dbPath = ".\db.sqlite"
if (Test-Path $dbPath) {
    Write-Host "`n✓ Database already exists" -ForegroundColor Green
} else {
    Write-Host "`nWarning: Database not found at $dbPath" -ForegroundColor Yellow
    Write-Host "Make sure the database schema has been created" -ForegroundColor Yellow
}

# Start the MCP server
Write-Host "`n================================" -ForegroundColor Cyan
Write-Host "Starting MCP Agent Coordinator" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server`n" -ForegroundColor Yellow

# Set environment variable for unbuffered output
$env:PYTHONUNBUFFERED = "1"

# Run the server
try {
    python server.py
} catch {
    Write-Host "`nServer stopped" -ForegroundColor Yellow
}

# Deactivate virtual environment on exit
deactivate 2>$null 