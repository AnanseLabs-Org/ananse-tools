"""
tools/cybops/kali.py
====================
CLI Client helper for verifying connection to the kali-server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import httpx

log = logging.getLogger(__name__)

_DEFAULT_SERVER = os.environ.get("KALI_SERVER_URL", "http://kali-server:8001/mcp")

def _cli_main() -> None:
    """
    Entry point for the ``mcp-server`` CLI tool.
    Runs a health check against the Kali FastMCP server and prints the result.
    """
    parser = argparse.ArgumentParser(
        prog="mcp-server",
        description="Verify connection to the Kali FastMCP server",
    )
    parser.add_argument(
        "--server",
        default=_DEFAULT_SERVER,
        help=f"Kali MCP server URL (default: {_DEFAULT_SERVER})",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _run():
        try:
            async with httpx.AsyncClient() as client:
                # FastMCP server responds with MCP init or tool list at /mcp
                # Check root or /health if mapped, let's probe /health first
                # (FastMCP doesn't map health by default, so we can check SSE/HTTP root)
                resp = await client.get(args.server, timeout=10)
                print(f"Status Code: {resp.status_code}")
                print(resp.text[:500])
        except Exception as exc:
            print(f"Error connecting to Kali server: {exc}")

    log.info("Connecting to Kali server at %s", args.server)
    asyncio.run(_run())


if __name__ == "__main__":
    _cli_main()

