#!/usr/bin/env pwsh
# Simple PowerShell wrapper to ensure virtual environment activation
Set-Location "C:\Development\cursor-agent-coordinator-mcp"
& ".\\.venv\\Scripts\\Activate.ps1"
& python server.py 