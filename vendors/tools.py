import math
import uuid
from datetime import datetime, timezone
from mcp.types import ToolAnnotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app import general as mcp
from http_client import _call_vendor_api
from db import _get_db
from payments.tools import momo_collect
from vendors.registry import (
    get_all_vendors,
    get_vendor_provider,
    _public_vendor_view,
    _expand_category_query
)




class VendorOrderItem(BaseModel):
    dish_id: Any = Field(..., description="The ID of the dish/item to order")
    quantity: int = Field(..., description="The quantity of the item to order")
    addon_ids: List[Any] = Field(default_factory=list, description="List of IDs of addons to include")


@mcp.tool(
    description=(
        "Place an order with a food/goods vendor. This creates a tracked order in MongoDB in PENDING_PAYMENT status "
        "and returns an order_id. Once created, you MUST call 'initiate_order_payment' to process the MoMo transaction. "
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
        ":returns: dict with success, order_id, total_amount, and pending instruction."
    ),
    tags={"role:vendors_user"},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
)
async def create_verified_vendors_order(
    *,
    vendor_id: str,
    items: List[VendorOrderItem],
    payment_number: Optional[str] = None,
    network: Optional[str] = None,
    momo_number: Optional[str] = None,
    momo_network: Optional[str] = None,
    customer_name: Optional[str] = None,
    order_type: str = "inhouse",
    table_number: Any = None,
    delivery_address: Any = None,
) -> Dict[str, Any]:
    """
    Place an order with a food/goods vendor and register it in MongoDB for tracked payment collection.
    """
    resolved_payment_number = payment_number or momo_number
    resolved_network = (network or momo_network).upper() if (network or momo_network) else None

    if not resolved_payment_number:
        return {"success": False, "error": "payment_number or momo_number is required"}
    if not resolved_network:
        return {"success": False, "error": "network or momo_network is required"}

    if table_number is not None:
        table_number = str(table_number).strip() or None
    if delivery_address is not None:
        delivery_address = str(delivery_address).strip() or None

    try:
        provider = await get_vendor_provider(vendor_id)
        if provider is None:
            return {"success": False, "error": f"No vendor provider found for id {vendor_id!r}"}

        if provider.vendor_type == "internal_service":
            return {
                "success": False,
                "error": f"Vendor {vendor_id!r} is a telecom service. Please use the dedicated purchase tools directly."
            }

        supported_order_types = provider.vendor_data.get("order_types", ["inhouse", "delivery"])
        if order_type not in supported_order_types:
            return {
                "success": False,
                "error": f"Vendor {vendor_id!r} does not support order_type {order_type!r} (supported: {supported_order_types})",
            }
        if order_type == "inhouse" and not table_number:
            return {"success": False, "error": "table_number is required for inhouse orders"}
        if order_type == "delivery" and not delivery_address:
            return {"success": False, "error": "delivery_address is required for delivery orders"}

        # Fetch menu to verify items and sum prices
        menu_items = await provider.get_menu()
        menu_by_id = {str(item["dish_id"]): item for item in menu_items}

        total_amount = 0.0
        serialized_items = []

        for line in items:
            dish_key = str(line.dish_id)
            dish = menu_by_id.get(dish_key)
            if dish is None:
                return {"success": False, "error": f"Item ID {line.dish_id!r} not found on vendor's menu"}
            if not dish.get("is_available", True):
                return {"success": False, "error": f"{dish['name']!r} is currently unavailable"}

            dish_price = float(dish.get("price") or 0.0)
            addons_sum = 0.0
            addons_detail = []
            for aid in line.addon_ids:
                addon = next((a for a in dish.get("addons", []) if str(a["addon_id"]) == str(aid)), None)
                if addon:
                    addons_sum += float(addon.get("price") or 0.0)
                    addons_detail.append({"addon_id": aid, "name": addon.get("name"), "price": addon.get("price")})

            item_total = (dish_price + addons_sum) * line.quantity
            total_amount += item_total

            serialized_items.append({
                "dish_id": line.dish_id,
                "name": dish["name"],
                "quantity": line.quantity,
                "price": dish_price,
                "addon_ids": line.addon_ids,
                "addons": addons_detail,
                "total": item_total
            })

        order_id = f"VND-{uuid.uuid4().hex[:8].upper()}"
        order_doc = {
            "order_id": order_id,
            "vendor_id": vendor_id,
            "vendor_name": provider.name,
            "items": serialized_items,
            "payment_number": resolved_payment_number,
            "network": resolved_network,
            "customer_name": customer_name,
            "order_type": order_type,
            "table_number": table_number,
            "delivery_address": delivery_address,
            "total_amount": total_amount,
            "status": "PENDING_PAYMENT",
            "created_at": datetime.now(timezone.utc)
        }

        db = _get_db()
        if db is not None:
            await db.orders.insert_one(order_doc)

        return {
            "success": True,
            "order_id": order_id,
            "total_amount": total_amount,
            "status": "PENDING_PAYMENT",
            "message": f"Order created. Please call initiate_order_payment with order_id {order_id!r} to pay."
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to register order: {str(e)}"}


@mcp.tool(
    description="Initiate the payment collection prompt on Mobile Money for a tracked order, and trigger vendor confirmation on success.",
    tags={"role:vendors_user"},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
)
async def initiate_order_payment(*, order_id: str) -> Dict[str, Any]:
    """
    Trigger BulkClix MoMo collection for a tracked order and create the order on the vendor endpoint on success.
    """
    db = _get_db()
    if db is None:
        return {"success": False, "error": "Database is unavailable. Cannot process tracked payment."}

    order = await db.orders.find_one({"order_id": order_id})
    if not order:
        return {"success": False, "error": f"Order ID {order_id!r} not found."}

    if order.get("status") != "PENDING_PAYMENT":
        return {
            "success": False,
            "error": f"Order {order_id!r} is not in PENDING_PAYMENT status (current status: {order.get('status')})"
        }

    vendor_id = order.get("vendor_id")
    provider = await get_vendor_provider(vendor_id)
    if provider is None:
        return {"success": False, "error": f"No vendor provider resolved for vendor_id {vendor_id!r}"}

    total_amount = order.get("total_amount")
    pay_number = order.get("payment_number")
    network = order.get("network")

    # 1. Trigger actual Mobile Money collection via BulkClix momo gateway
    momo_result = await momo_collect(
        amount=total_amount,
        phone_number=pay_number,
        network=network,
        transaction_id=order_id,
        reference=order_id
    )

    # In a full production loop, we would await webhook/callback verification.
    # For integration flow, we proceed directly to vendor creation if prompt is successfully dispatched.
    is_momo_success = (
        momo_result.get("success") is True 
        or "Payment Initiated Successful" in momo_result.get("message", "")
        or momo_result.get("status") == "PENDING"
    )
    if not is_momo_success:
        return {
            "success": False,
            "error": "Mobile Money prompt initiation failed.",
            "details": momo_result
        }

    # 2. Dispatch the paid order to the vendor provider
    vendor_payload = {
        "order_type": order.get("order_type"),
        "table_number": order.get("table_number"),
        "delivery_address": order.get("delivery_address"),
        "payment_number": pay_number,
        "network": network,
        "items": order.get("items", [])
    }
    
    vendor_result = await provider.create_order(vendor_payload)
    new_status = "PAID" if vendor_result.get("success", False) else "PAYMENT_INITIATED_VENDOR_ERROR"

    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {
            "status": new_status,
            "momo_collection": momo_result,
            "vendor_dispatch": vendor_result
        }}
    )

    return {
        "success": True,
        "order_id": order_id,
        "payment_status": "MOMO_PROMPT_SENT",
        "vendor_status": new_status,
        "momo_result": momo_result,
        "vendor_result": vendor_result
    }


# ── Shopify-Specific Metadata Tools ────────────────────────────────────────

@mcp.tool(
    description="Fetch a Shopify customer details by customer_id. :param vendor_id: Shopify Vendor UUID. :param customer_id: Customer's Shopify ID.",
    tags={"role:vendors_user"},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def get_shopify_customer(*, vendor_id: str, customer_id: str) -> Dict[str, Any]:
    provider = await get_vendor_provider(vendor_id)
    if not provider or not isinstance(provider, ShopifyVendorProvider):
        return {"success": False, "error": "Resolved vendor is not a Shopify vendor"}
    res = await provider.get_customer(customer_id)
    return {"success": True, "customer": res}


@mcp.tool(
    description="List active orders from a Shopify store. :param vendor_id: Shopify Vendor UUID.",
    tags={"role:vendors_user"},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def get_shopify_orders(*, vendor_id: str) -> Dict[str, Any]:
    provider = await get_vendor_provider(vendor_id)
    if not provider or not isinstance(provider, ShopifyVendorProvider):
        return {"success": False, "error": "Resolved vendor is not a Shopify vendor"}
    res = await provider.get_orders()
    return {"success": True, "orders": res}


@mcp.tool(
    description="Retrieve product collections from a Shopify store. :param vendor_id: Shopify Vendor UUID.",
    tags={"role:vendors_user"},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def get_shopify_collections(*, vendor_id: str) -> Dict[str, Any]:
    provider = await get_vendor_provider(vendor_id)
    if not provider or not isinstance(provider, ShopifyVendorProvider):
        return {"success": False, "error": "Resolved vendor is not a Shopify vendor"}
    res = await provider.get_collections()
    return {"success": True, "collections": res}


@mcp.tool(
    description="Query metafields for a resource in Shopify. :param vendor_id: Shopify Vendor UUID. :param owner_resource: E.g. 'products', 'collections', 'customers', 'orders'. :param owner_id: The ID of the resource owner.",
    tags={"role:vendors_user"},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def get_shopify_metafields(*, vendor_id: str, owner_resource: str, owner_id: str) -> Dict[str, Any]:
    provider = await get_vendor_provider(vendor_id)
    if not provider or not isinstance(provider, ShopifyVendorProvider):
        return {"success": False, "error": "Resolved vendor is not a Shopify vendor"}
    res = await provider.get_metafields(owner_resource, owner_id)
    return {"success": True, "metafields": res}


@mcp.tool(
    description="Search for food items, dishes, pizza, rice, chicken, or menus across all verified vendors or a specific vendor. Use this when asking 'what food is available', 'show me the menu', 'do you have pizza', 'search menu for burger'.",
    tags={"role:vendors_user"},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def find_food_items(
    *,
    query: str,
    vendor_id: Any = None
) -> Dict[str, Any]:
    """
    Search for food items, dishes, pizza, rice, chicken, or menus across all verified vendors or a specific vendor.
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
    tags={"role:vendors_user"},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def list_vendor_categories() -> Dict[str, Any]:
    """
    List all categories of goods (e.g. 'restaurant', 'food', 'airtime', 'data') supported by the verified vendors.
    """
    vendors = await get_all_vendors()
    categories = set()
    for v in vendors:
        categories.update(v.get("categories", []))
    return {
        "success": True,
        "categories": sorted(list(categories))
    }
