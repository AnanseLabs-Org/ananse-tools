import sys
from app import mcp, FastMCP
from starlette.routing import Route

print("Routes:")
for route in mcp.http_app.routes:
    if isinstance(route, Route):
        print(route.path)
    else:
        print(route)
