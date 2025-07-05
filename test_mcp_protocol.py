#!/usr/bin/env python3
"""
Test script to verify MCP protocol communication
"""
import asyncio
import json
import sys
import subprocess
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def test_mcp_server():
    """Test MCP server communication using subprocess"""
    print("Testing MCP server communication...")

    try:
        # Start server process
        cmd = ["uv", "run", "python", "main.py"]
        env = {
            "OSM_USE_DEV_API": "true",
            "LOG_LEVEL": "INFO"
        }

        print(f"Starting server with command: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).parent),
            env={**dict(os.environ), **env},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Send initialization request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }

        print("Sending initialization request...")
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()

        # Read response
        response_line = process.stdout.readline()
        if response_line:
            response = json.loads(response_line)
            print(f"✅ Initialization response: {response}")

            # Send initialized notification (required by MCP protocol)
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }

            print("Sending initialized notification...")
            process.stdin.write(json.dumps(initialized_notification) + "\n")
            process.stdin.flush()

            # Small delay to ensure server is ready
            await asyncio.sleep(0.1)

        else:
            print("❌ No response received")

        # Send tools list request
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        print("Sending tools list request...")
        process.stdin.write(json.dumps(tools_request) + "\n")
        process.stdin.flush()

        # Read response
        response_line = process.stdout.readline()
        if response_line:
            response = json.loads(response_line)
            if "result" in response and "tools" in response["result"]:
                tools = response["result"]["tools"]
                print(f"✅ Found {len(tools)} tools:")
                for tool in tools[:5]:  # Show first 5 tools
                    print(f"  - {tool['name']}: {tool.get('description', 'No description')}")
                if len(tools) > 5:
                    print(f"  ... and {len(tools) - 5} more tools")

                # Test calling a simple tool
                print("\nTesting get_server_info tool...")
                tool_call_request = {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "get_server_info",
                        "arguments": {}
                    }
                }

                process.stdin.write(json.dumps(tool_call_request) + "\n")
                process.stdin.flush()

                # Read tool response
                tool_response_line = process.stdout.readline()
                if tool_response_line:
                    tool_response = json.loads(tool_response_line)
                    if "result" in tool_response:
                        print(f"✅ Tool call successful: {tool_response['result']}")
                    else:
                        print(f"❌ Tool call failed: {tool_response}")

            else:
                print(f"❌ Unexpected response: {response}")
        else:
            print("❌ No response received")

        # Clean up
        process.terminate()
        process.wait()

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import os
    success = asyncio.run(test_mcp_server())
    sys.exit(0 if success else 1)