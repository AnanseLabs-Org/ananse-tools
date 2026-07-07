"""
kali_server — Kali Linux Computer Server package.

Lives at tools/servers/kali_server/ inside the repo.

Installed only in the kali-server container; provides the
``kali-server-mcp`` Flask API entry point (server.py).

The MCP-side client (KaliClient + mcp-server CLI) lives at
tools/cybops/kali.py and is installed via the main ananse-mcp package.
"""
