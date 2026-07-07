from mcp.types import ToolAnnotations
from typing import Any, Dict
from app import general as mcp
from integrations.yango.widget import build_ride_widget_link

@mcp.tool(
    description="Get a Yango booking link for a delivery between two points. The customer opens this link to confirm pickup/dropoff and pricing in the Yango app — pricing and order placement happen on Yango's side, not through this server, until direct API access is enabled.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def get_yango_delivery_link(
    *, pickup_lat: float, pickup_lon: float, dropoff_lat: float, dropoff_lon: float,
) -> Dict[str, Any]:
    """
    Get a Yango booking link for a delivery between two points. The customer
    opens this link to confirm pickup/dropoff and pricing in the Yango app —
    pricing and order placement happen on Yango's side, not through this
    server, until direct API access is enabled.
    """
    link = build_ride_widget_link(
        start_lat=pickup_lat, start_lon=pickup_lon,
        end_lat=dropoff_lat, end_lon=dropoff_lon,
    )
    return {
        "success": True,
        "booking_link": link,
        "note": "Opens Yango's app/site to confirm pricing and complete the booking.",
    }
