import math
from mcp.types import ToolAnnotations
from typing import Any, Dict, List, Optional
from app import general as mcp
from http_client import _call_vendor_api
from vendors.registry import (
    STATIC_VENDORS_LIST,
    _lookup_vendor,
    _public_vendor_view,
    _expand_category_query
)
from vendors.menu import _flatten_menu

@mcp.tool(
    description="List available vendors to purchase goods from using BulkClix payment. :param vendor_id: Vendor's UUID. If given, returns just that vendor. :param category: Vendor's category of goods (e.g. 'restaurant', 'food', 'airtime'). If given, filters vendors using case-insensitive substring and synonym expansion. :param page: Page number for pagination (default 1). :param page_size: Page size for pagination (default 10).",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def get_verified_vendors(
    *,
    vendor_id: Any = None,
    category: Any = None,
    page: int = 1,
    page_size: int = 10,
) -> Dict[str, Any]:
    """
    List available vendors to purchase goods from using BulkClix payment.
    :param vendor_id: Vendor's UUID. If given, returns just that vendor.
    :param category: Vendor's category of goods (e.g. "restaurant", "food", "airtime").
        If given, filters vendors using case-insensitive substring and synonym expansion.
    :param page: Page number for pagination (default 1).
    :param page_size: Page size for pagination (default 10).
    """
    if not isinstance(vendor_id, str):
        vendor_id = None
    if not isinstance(category, str):
        category = None

    if vendor_id:
        vendor = _lookup_vendor(vendor_id)
        if vendor is None:
            return {"success": False, "error": f"No vendor found with id {vendor_id!r}"}
        return {"success": True, "vendors": [_public_vendor_view(vendor)]}

    vendors = STATIC_VENDORS_LIST
    if category:
        q_expanded = _expand_category_query(category)
        vendors = [
            v for v in vendors
            if any(
                any(syn in c.lower() or c.lower() in syn for syn in q_expanded)
                for c in v.get("categories", [])
            )
        ]

    total = len(vendors)
    start = (page - 1) * page_size
    paginated = vendors[start : start + page_size]

    return {
        "success": True,
        "vendors": [_public_vendor_view(v) for v in paginated],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size),
            "has_next": start + page_size < total,
        }
    }


@mcp.tool(
    description="List available menu items for a vendor, flattened and checkout-ready — each item has dish_id, name, price, is_available, and addons. No nested categories. :param vendor_id: Vendor's UUID. :param query: Optional case-insensitive substring filter on dish name. :param page: Page number for pagination (default 1). :param page_size: Page size for pagination (default 10).",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def get_verified_vendors_menu(
    *,
    vendor_id: str,
    query: Any = None,
    page: int = 1,
    page_size: int = 10,
) -> Dict[str, Any]:
    """
    List available menu items for a vendor, flattened and checkout-ready —
    each item has dish_id, name, price, is_available, and addons. No nested categories.
    :param vendor_id: Vendor's UUID.
    :param query: Optional case-insensitive substring filter on dish name.
    :param page: Page number for pagination (default 1).
    :param page_size: Page size for pagination (default 10).
    """
    if not isinstance(query, str):
        query = None

    vendor = _lookup_vendor(vendor_id)
    if vendor is None:
        return {"success": False, "error": f"No vendor found with id {vendor_id!r}"}

    # Branch for internal services (e.g., Airtime & Data)
    if vendor.get("vendor_type") == "internal_service":
        return {
            "success": True,
            "items": [],
            "note": f"{vendor['name']} is an internal service. Please use the dedicated tools (airtime_purchase, data_purchase, or data_get_bundles) to query packages and buy."
        }

    raw_response = await _call_vendor_api("GET", vendor["menu_url"])

    if isinstance(raw_response, dict) and raw_response.get("success") is False:
        return raw_response

    if not isinstance(raw_response, list):
        return {"success": False, "error": "Unexpected menu response shape from vendor"}

    items = _flatten_menu(raw_response)

    if query:
        q = query.lower()
        items = [i for i in items if q in (i["name"] or "").lower()]

    total = len(items)
    start = (page - 1) * page_size
    paginated = items[start : start + page_size]

    return {
        "success": True,
        "items": paginated,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size),
            "has_next": start + page_size < total,
        }
    }


from pydantic import BaseModel, Field

class VendorOrderItem(BaseModel):
    dish_id: int = Field(..., description="The integer ID of the dish/item to order")
    quantity: int = Field(..., description="The quantity of the item to order")
    addon_ids: List[int] = Field(default_factory=list, description="List of integer IDs of addons to include")

@mcp.tool(
    description=(
        "Place an order with a food/goods vendor and initiate mobile money payment via BulkClix. "
        "IMPORTANT: Before calling this tool you MUST have collected ALL required fields from the user: "
        "(1) if order_type='inhouse' — you MUST ask the user for their table_number first; "
        "(2) if order_type='delivery' — you MUST ask the user for their delivery_address first. "
        "Do NOT call this tool without those values — the tool will fail. "
        ":param vendor_id: Vendor's UUID. "
        ":param items: List of items to order, with dish_id, quantity, and addon_ids. "
        ":param payment_number: Mobile money number to charge (e.g. '0544929180'). "
        ":param network: Mobile money network code (e.g. 'MTN'). "
        ":param order_type: 'inhouse' or 'delivery' — must be one of the vendor's supported order_types. "
        ":param table_number: Table number string. REQUIRED when order_type is 'inhouse' — ask the user before calling. "
        ":param delivery_address: Delivery address string. REQUIRED when order_type is 'delivery' — ask the user before calling. "
        ":returns: dict with success, order_id, payment status, and vendor confirmation."
    ),
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
)
async def create_verified_vendors_order(
    *,
    vendor_id: str,
    items: List[VendorOrderItem],
    payment_number: str,
    network: str,
    order_type: str = "inhouse",
    table_number: Any = None,
    delivery_address: Any = None,
) -> Dict[str, Any]:
    """
    Place an order with a food/goods vendor and initiate mobile money payment via BulkClix.
    :param vendor_id: Vendor's UUID.
    :param items: List of items to order, with dish_id, quantity, and addon_ids.
    :param payment_number: Mobile money number to charge (e.g. "0544929180").
    :param network: Mobile money network code (e.g. "MTN").
    :param order_type: "inhouse" or "delivery" — must be one of the vendor's supported order_types.
    :param table_number: Table number. Required when order_type is "inhouse".
    :param delivery_address: Delivery address. Required when order_type is "delivery".
    """
    # Coerce to str so integer table numbers (e.g. 1) are accepted
    if table_number is not None:
        table_number = str(table_number).strip() or None
    if delivery_address is not None:
        delivery_address = str(delivery_address).strip() or None

    try:
        vendor = _lookup_vendor(vendor_id)
        if vendor is None:
            return {"success": False, "error": f"No vendor found with id {vendor_id!r}"}

        # Branch for internal services
        if vendor.get("vendor_type") == "internal_service":
            return {
                "success": False,
                "error": f"Vendor {vendor_id!r} is a telecom service. Please use the dedicated purchase tools directly (airtime_purchase, data_purchase) instead of this vendor order tool."
            }

        if "momo" not in vendor.get("payment_methods", []):
            return {"success": False, "error": f"Vendor {vendor_id!r} does not support mobile money payment"}

        supported_order_types = vendor.get("order_types", [])
        if order_type not in supported_order_types:
            return {
                "success": False,
                "error": f"Vendor {vendor_id!r} does not support order_type {order_type!r} "
                         f"(supported: {supported_order_types})",
            }
        if order_type == "inhouse" and not table_number:
            return {"success": False, "error": "table_number is required for inhouse orders"}
        if order_type == "delivery" and not delivery_address:
            return {"success": False, "error": "delivery_address is required for delivery orders"}

        # We can pass pagination params to get all items to verify
        menu_result = await get_verified_vendors_menu(vendor_id=vendor_id, page=1, page_size=1000)
        if not menu_result["success"]:
            return {"success": False, "error": f"Could not verify menu before ordering: {menu_result['error']}"}

        menu_by_id = {item["dish_id"]: item for item in menu_result["items"]}
        for line in items:
            dish = menu_by_id.get(line.dish_id)
            if dish is None:
                return {"success": False, "error": f"dish_id {line.dish_id!r} not found on vendor's menu"}
            if not dish["is_available"]:
                return {"success": False, "error": f"{dish['name']!r} (dish_id {dish['dish_id']}) is currently unavailable"}

        order_url = vendor.get("order_url")
        if not order_url:
            return {"success": False, "error": f"Vendor {vendor_id!r} has no configured order endpoint"}

        payload = {
            "order_type": order_type,
            "table_number": table_number,
            "items": [item.model_dump() for item in items],
            "payment_number": payment_number,
            "network": network,
        }
        if order_type == "delivery":
            payload["delivery_address"] = delivery_address

        return await _call_vendor_api("POST", order_url, json=payload)
    except Exception as e:
        return {"success": False, "error": f"Unexpected error placing order: {e}"}


@mcp.tool(
    description="Search for food items, dishes, pizza, rice, chicken, or menus across all verified vendors or a specific vendor. Use this when asking 'what food is available', 'show me the menu', 'do you have pizza', 'search menu for burger'.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def find_food_items(
    *,
    query: str,
    vendor_id: Any = None
) -> Dict[str, Any]:
    """
    Search for food items, dishes, pizza, rice, chicken, or menus across all verified vendors or a specific vendor.
    Use this when asking 'what food is available', 'show me the menu', 'do you have pizza', 'search menu for burger'.
    """
    if not isinstance(vendor_id, str):
        vendor_id = None

    try:
        from tools.search import search as semantic_search
        res = await semantic_search(query=query, vendor_id=vendor_id)
        if not res.get("success"):
            return res
        items = res.get("menu_items", [])
        return {"success": True, "query": query, "total_matches": len(items), "items": items}
    except Exception as e:
        return {"success": False, "error": f"Semantic search failed: {str(e)}"}


@mcp.tool(
    description="List all categories of goods (e.g. 'restaurant', 'food', 'airtime', 'data') supported by the verified vendors.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def list_vendor_categories() -> Dict[str, Any]:
    """
    List all categories of goods (e.g. 'restaurant', 'food', 'airtime', 'data') supported by the verified vendors.
    """
    categories = set()
    for v in STATIC_VENDORS_LIST:
        categories.update(v.get("categories", []))
    return {
        "success": True,
        "categories": sorted(list(categories))
    }
