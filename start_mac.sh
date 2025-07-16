#!/bin/bash
# MCP Agent Coordinator - macOS Startup Script
# This script sets up the environment and starts the MCP server

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}================================${NC}"
echo -e "${CYAN}MCP Agent Coordinator Setup${NC}"
echo -e "${CYAN}================================${NC}"

# Check if Python is installed
echo -e "\n${YELLOW}Checking Python installation...${NC}"

# First check for python3 (preferred)
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}Error: Python is not installed${NC}"
    echo -e "${YELLOW}Please install Python 3.8 or higher:${NC}"
    echo -e "${YELLOW}Option 1: Install from python.org:${NC}"
    echo -e "${YELLOW}  Visit https://www.python.org/downloads/macos/${NC}"
    echo -e "${YELLOW}Option 2: Install using Homebrew:${NC}"
    echo -e "${YELLOW}  brew install python3${NC}"
    echo -e "${YELLOW}Option 3: Install using MacPorts:${NC}"
    echo -e "${YELLOW}  sudo port install python39${NC}"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
MAJOR_VERSION=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR_VERSION=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR_VERSION" -lt 3 ] || ([ "$MAJOR_VERSION" -eq 3 ] && [ "$MINOR_VERSION" -lt 8 ]); then
    echo -e "${RED}Error: Python 3.8 or higher is required. Found: Python $PYTHON_VERSION${NC}"
    echo -e "${YELLOW}Please upgrade Python using one of the methods above${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python found: $($PYTHON_CMD --version)${NC}"

# Check if pip is installed
echo -e "\n${YELLOW}Checking pip installation...${NC}"
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo -e "${YELLOW}pip not found. Installing pip...${NC}"
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    $PYTHON_CMD get-pip.py
    rm get-pip.py
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to install pip${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}✓ pip is available${NC}"

# Check if venv module is available
echo -e "\n${YELLOW}Checking Python venv module...${NC}"
if ! $PYTHON_CMD -m venv --help &> /dev/null; then
    echo -e "${RED}Error: Python venv module is not available${NC}"
    echo -e "${YELLOW}This should be included with Python 3.3+${NC}"
    echo -e "${YELLOW}Try reinstalling Python from python.org${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python venv module available${NC}"

# Set up virtual environment
VENV_PATH=".venv"
if [ -d "$VENV_PATH" ]; then
    echo -e "\n${GREEN}✓ Virtual environment already exists${NC}"
else
    echo -e "\n${YELLOW}Creating virtual environment...${NC}"
    $PYTHON_CMD -m venv $VENV_PATH
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to create virtual environment${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate virtual environment
echo -e "\n${YELLOW}Activating virtual environment...${NC}"
source $VENV_PATH/bin/activate
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Virtual environment activated${NC}"
else
    echo -e "${RED}Error: Failed to activate virtual environment${NC}"
    exit 1
fi

# Upgrade pip
echo -e "\n${YELLOW}Upgrading pip...${NC}"
python -m pip install --upgrade pip --quiet
echo -e "${GREEN}✓ Pip upgraded${NC}"

# Install wheel to prevent build issues
echo -e "\n${YELLOW}Installing wheel...${NC}"
pip install wheel --quiet
echo -e "${GREEN}✓ Wheel installed${NC}"

# Install MCP SDK
echo -e "\n${YELLOW}Installing MCP SDK...${NC}"
if pip list 2>/dev/null | grep -q "^mcp "; then
    echo -e "${GREEN}✓ MCP SDK already installed${NC}"
else
    pip install mcp
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to install MCP SDK${NC}"
        echo -e "${YELLOW}Trying alternative installation method...${NC}"
        pip install "mcp @ git+https://github.com/modelcontextprotocol/python-sdk.git"
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Could not install MCP SDK${NC}"
            exit 1
        fi
    fi
    echo -e "${GREEN}✓ MCP SDK installed${NC}"
fi

# Check if database exists
DB_PATH="./db.sqlite"
if [ -f "$DB_PATH" ]; then
    echo -e "\n${GREEN}✓ Database already exists${NC}"
else
    echo -e "\n${YELLOW}Warning: Database not found at $DB_PATH${NC}"
    echo -e "${YELLOW}Make sure the database schema has been created${NC}"
fi

# Function to handle cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Server stopped${NC}"
    deactivate 2>/dev/null
    exit 0
}

# Set up signal handlers
trap cleanup INT TERM

# Start the MCP server
echo -e "\n${CYAN}================================${NC}"
echo -e "${CYAN}Starting MCP Agent Coordinator${NC}"
echo -e "${CYAN}================================${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}\n"

# Set environment variable for unbuffered output
export PYTHONUNBUFFERED=1

# Run the server
python server.py

# Cleanup will be called by trap 