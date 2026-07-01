#!/usr/bin/env python3
"""
BulkClix MCP Server (Modularized Edition)
=========================================
An AI agent portal for interacting with the BulkClix platform.
Imports modules to trigger FastMCP tool registrations.
"""

import sys
from app import mcp

# Import tools for their registration side-effects
from tools import sms as _sms  # noqa: F401
from tools import otp as _otp  # noqa: F401
from tools import airtime as _airtime  # noqa: F401
from tools import bank as _bank  # noqa: F401
from tools import data_bundles as _data_bundles  # noqa: F401
from tools import kyc as _kyc  # noqa: F401
from tools import contacts as _contacts  # noqa: F401
from tools import account as _account  # noqa: F401
from tools import food_orders as _food_orders  # noqa: F401

from payments import tools as _payment_tools  # noqa: F401
from vendors import tools as _vendor_tools  # noqa: F401
from integrations.yango import tools as _yango_tools  # noqa: F401

def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1].lower() in {"mcp", "sse"}:
        print("Starting ananse-mcp on SSE transport...", file=sys.stderr)
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()