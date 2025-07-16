#!/usr/bin/env python3
"""Test script for the fixed MCP server"""

import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_server():
    """Test if the fixed server properly registers tools"""
    print("Testing fixed server...")
    
    # Import the server module
    import mcp_server_fixed
    
    # Get the tools
    try:
        tools = await mcp_server_fixed.handle_list_tools()
        print(f"\n✅ Found {len(tools)} tools:")
        for i, tool in enumerate(tools, 1):
            print(f"  {i}. {tool.name} - {tool.description}")
        
        # Test a simple tool call
        result = await mcp_server_fixed.handle_call_tool("get_instructions", {})
        print(f"\n✅ Tool call test successful!")
        print(f"Instructions length: {len(result[0].text)} characters")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_server())
    if success:
        print(f"\n🎉 Fixed server is working correctly!")
    else:
        print("\n💥 Fixed server has issues!") 