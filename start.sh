#!/bin/bash
# Unified MCP Agent Coordinator Startup Script for Unix systems

# Parse command line arguments
STDIO=false
SERVER_HOST="127.0.0.1"
PORT="8001"

while [[ $# -gt 0 ]]; do
    case $1 in
        --stdio)
            STDIO=true
            shift
            ;;
        --host)
            SERVER_HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--stdio] [--host HOST] [--port PORT]"
            exit 1
            ;;
    esac
done

echo "================================"
echo "MCP Agent Coordinator Server"
echo "================================"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Set environment variables and start server
if [ "$STDIO" = true ]; then
    export USE_STDIO="true"
    echo ""
    echo "🚀 Starting MCP Agent Coordinator in stdio mode"
    echo "🔧 Configure in Cursor with stdio transport"
    echo "📡 Available tools: 12 coordination tools"
    echo "Press Ctrl+C to stop the server"
else
    export USE_STDIO="false"
    export MCP_SERVER_HOST="$SERVER_HOST"
    export MCP_SERVER_PORT="$PORT"
    echo ""
    echo "🚀 Starting MCP Agent Coordinator on http://$SERVER_HOST:$PORT"
    echo "🔧 Use this URL in your Cursor MCP configuration:"
    echo "   {\"mcpServers\": {\"agent-coordinator\": {\"url\": \"http://$SERVER_HOST:$PORT\"}}}"
    echo "📡 Available tools: 12 coordination tools"
    echo "Press Ctrl+C to stop the server"
fi

echo ""

# Start the server
python3 main.py 