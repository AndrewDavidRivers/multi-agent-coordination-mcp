#!/usr/bin/env python3
"""Test script to verify MCP server tools registration"""

import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_server_stdio import AgentCoordinatorServer

async def test_server():
    """Test if the server properly registers tools"""
    print("Creating server...")
    server = AgentCoordinatorServer()
    
    print("Server created successfully!")
    print(f"Server object: {server}")
    print(f"MCP Server object: {server.server}")
    
    # Test tool listing
    try:
        tools = await server.server._tool_handlers['list_tools']()
        print(f"\n✅ Found {len(tools)} tools:")
        for i, tool in enumerate(tools, 1):
            print(f"  {i}. {tool.name} - {tool.description}")
            
        return True
    except Exception as e:
        print(f"❌ Error listing tools: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_server())
    if success:
        print(f"\n🎉 Server is working correctly with {len(asyncio.run(AgentCoordinatorServer().server._tool_handlers['list_tools']()))} tools!")
    else:
        print("\n💥 Server has issues!") 