#!/usr/bin/env python3
"""
Explains how MCP servers work and how to use this one
"""

print("""
🌐 Understanding MCP (Model Context Protocol) Servers
=====================================================

MCP servers are NOT traditional web servers! Here's how they work:

1️⃣  **Communication Method**: stdin/stdout (not HTTP)
   - MCP clients start the server as a subprocess
   - Communication uses JSON-RPC over stdin/stdout
   - No network ports, no web interface

2️⃣  **How to Use This Server**:
   
   Option A: Configure in an MCP Client
   ----------------------------------------
   • Cursor IDE → Settings → Features → MCP
   • Claude Desktop → Add to config file
   • VSCode (Cline) → Add to settings.json
   • Continue.dev → Add to config.json
   
   The client will start/stop the server automatically!

   Option B: Test Without a Client
   ----------------------------------------
   • Run: python test_comprehensive.py
   • Run: python quick_test.py
   • These scripts test the server's functionality

3️⃣  **Why "python main.py" Appears to Hang**:
   - It's waiting for JSON-RPC input on stdin
   - This is normal! It's meant to be started by a client
   - Use the test scripts instead for direct testing

4️⃣  **Configuration Example (Cursor)**:
   {
     "mcpServers": {
       "osm-edit": {
         "command": "uv",
         "args": ["run", "python", "/path/to/osm-edit-mcp/main.py"],
         "cwd": "/path/to/osm-edit-mcp"
       }
     }
   }

📚 For detailed setup instructions, see:
   - docs/MCP_CLIENT_SETUP.md
   - docs/RUNNING_SERVER.md
   - QUICK_REFERENCE.md

✅ Ready to test? Run: python test_comprehensive.py
""")