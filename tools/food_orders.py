from mcp.types import ToolAnnotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4
from app import general as mcp
from db import _get_db
from tools.sms import sms_send
from payments.tools import momo_collect
from vendors.registry import STATIC_VENDORS_LIST

@mcp.tool(
    description="Search food dishes and restaurants across available catalogs in a specified city (e.g. Accra). Currently searches verified vendors matching categories or name.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def search_food_menus(query: str, city: str = "accra") -> Dict[str, Any]:
    """
    Search food dishes and restaurants across available catalogs in a specified city (e.g. Accra).
    Currently searches verified vendors matching categories or name.
    """
    try:
        results = []
        q_lower = query.lower()
        
        # Search local static vendors
        for vendor in STATIC_VENDORS_LIST:
            v_name = vendor.get("name", "")
            cats = vendor.get("categories", [])
            if q_lower in v_name.lower() or any(q_lower in c.lower() for c in cats):
                # Skip telecom services
                if vendor.get("vendor_type") == "internal_service":
                    continue
                results.append({
                    "source": "Registered Vendor",
                    "vendor_id": vendor.get("vendor_id"),
                    "restaurant_name": v_name,
                    "categories": cats,
                    "payment_methods": vendor.get("payment_methods", [])
                })
                        
        return {
            "success": True,
            "city": city,
            "query": query,
            "total_matches": len(results),
            "matches": results
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to search food menus: {e}"}


@mcp.tool(
    description="Save or update a customer profile in MongoDB, including delivery address, landmark, and default MoMo payment number.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
)
async def save_customer_profile(
    customer_name: str,
    phone_number: str,
    address: str,
    landmark: str = None,
    default_payment_phone: str = None
) -> Dict[str, Any]:
    """
    Save or update a customer profile in MongoDB, including delivery address, landmark, and default MoMo payment number.
    """
    try:
        db = _get_db()
        profile_data = {
            "customer_name": customer_name,
            "phone_number": phone_number,
            "address": address,
            "landmark": landmark,
            "default_payment_phone": default_payment_phone or phone_number,
            "updated_at": datetime.now(timezone.utc)
        }
        if db is not None:
            await db.profiles.update_one({"phone_number": phone_number}, {"$set": profile_data}, upsert=True)
            storage_status = "persisted_to_mongodb"
        else:
            storage_status = "memory_only_mongodb_unavailable"

        return {
            "success": True,
            "storage_status": storage_status,
            "profile": profile_data
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to save customer profile: {e}"}


@mcp.tool(
    description="Retrieve a saved customer profile from MongoDB by phone number to get delivery address and payment preferences.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def get_customer_profile(phone_number: str) -> Dict[str, Any]:
    """
    Retrieve a saved customer profile from MongoDB by phone number to get delivery address and payment preferences.
    """
    try:
        db = _get_db()
        if db is not None:
            profile = await db.profiles.find_one({"phone_number": phone_number}, {"_id": 0})
            if profile:
                return {"success": True, "found": True, "profile": profile}
        return {"success": True, "found": False, "message": f"No saved profile found for phone number {phone_number}."}
    except Exception as e:
        return {"success": False, "error": f"Failed to retrieve customer profile: {e}"}


from typing import List
from pydantic import BaseModel, Field

class MerchantOrderItem(BaseModel):
    name: str = Field(..., description="The name of the food item or dish")
    quantity: int = Field(..., description="The quantity of the item to order")
    notes: Optional[str] = Field(None, description="Optional special instructions (e.g. 'no onions')")

@mcp.tool(
    description="Place a food order directly with a restaurant merchant. Creates an order record in MongoDB, triggers MoMo payment collection from customer, and sends an order SMS dispatch to the merchant.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
)
async def place_merchant_order(
    *,
    restaurant_phone: str,
    items: List[MerchantOrderItem],
    customer_name: str,
    customer_phone: str,
    delivery_address: str,
    amount_ghc: float,
    payment_phone: str = None,
    payment_network: str = "MTN"
) -> Dict[str, Any]:
    """
    Place a food order directly with a restaurant merchant.
    Creates an order record in MongoDB, triggers MoMo payment collection from customer, and sends an order SMS dispatch to the merchant.
    """
    try:
        order_id = f"ORD-{uuid4().hex[:8].upper()}"
        pay_phone = payment_phone or customer_phone
        
        # Serialize list of items for DB and SMS representation
        serialized_items = [item.model_dump() for item in items]
        items_summary = ", ".join([f"{item.quantity}x {item.name}" + (f" ({item.notes})" if item.notes else "") for item in items])
        
        order_doc = {
            "order_id": order_id,
            "restaurant_phone": restaurant_phone,
            "items": serialized_items,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "delivery_address": delivery_address,
            "payment_phone": pay_phone,
            "payment_network": payment_network,
            "amount_ghc": amount_ghc,
            "status": "PENDING_PAYMENT",
            "created_at": datetime.now(timezone.utc)
        }
        
        db = _get_db()
        if db is not None:
            await db.orders.insert_one(order_doc)
            
        # 1. Trigger actual Mobile Money collection
        momo_result = await momo_collect(
            amount=amount_ghc,
            phone_number=pay_phone,
            network=payment_network,
            transaction_id=order_id,
            reference=f"Order {order_id}"
        )
        
        # 2. Dispatch SMS to restaurant merchant via BulkClix SMS engine
        sms_msg = (
            f"NEW ORDER [{order_id}]\n"
            f"Customer: {customer_name} ({customer_phone})\n"
            f"Items: {items_summary}\n"
            f"Delivery Address: {delivery_address}\n"
            f"Payment Status: MoMo prompt sent to {pay_phone} ({payment_network})"
        )
        
        sms_result = await sms_send(message=sms_msg, recipients=[restaurant_phone])
        
        # Update status in DB - MoMo is only initiated, so status is PAYMENT_INITIATED_SMS_DISPATCHED
        new_status = "PAYMENT_INITIATED_SMS_DISPATCHED" if (sms_result.get("success") or "campaign_id" in sms_result) else "PENDING_RETRY"
        if db is not None:
            await db.orders.update_one(
                {"order_id": order_id}, 
                {"$set": {"status": new_status, "momo_initiation": momo_result, "sms_dispatch": sms_result}}
            )

        return {
            "success": True,
            "order_id": order_id,
            "status": new_status,
            "amount_ghc": amount_ghc,
            "momo_prompt_sent_to": pay_phone,
            "momo_collection_result": momo_result,
            "merchant_sms_result": sms_result
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to place merchant order: {e}"}


@mcp.tool(
    description="Track real-time status and delivery details of an order from MongoDB.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
)
async def track_order(order_id: str) -> Dict[str, Any]:
    """
    Track real-time status and delivery details of an order from MongoDB.
    """
    try:
        db = _get_db()
        if db is not None:
            order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
            if order:
                return {"success": True, "found": True, "order": order}
        return {"success": True, "found": False, "message": f"Order ID {order_id!r} not found in tracking database."}
    except Exception as e:
        return {"success": False, "error": f"Failed to track order: {e}"}


@mcp.tool(tags={"admin"}, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def update_order_status(order_id: str, status: str) -> Dict[str, Any]:
    """
    [Internal Tool] Update the delivery lifecycle status of an order (e.g. CONFIRMED, IN_TRANSIT, DELIVERED).
    """
    try:
        db = _get_db()
        valid_statuses = {"PENDING_PAYMENT", "PAYMENT_INITIATED_SMS_DISPATCHED", "CONFIRMED", "IN_TRANSIT", "DELIVERED", "CANCELLED"}
        if status.upper() not in valid_statuses:
            return {"success": False, "error": f"Invalid status {status!r}. Must be one of {valid_statuses}"}
            
        if db is not None:
            res = await db.orders.update_one({"order_id": order_id}, {"$set": {"status": status.upper()}})
            if res.matched_count > 0:
                return {"success": True, "order_id": order_id, "new_status": status.upper()}
        return {"success": False, "error": f"Order ID {order_id!r} not found."}
    except Exception as e:
        return {"success": False, "error": f"Failed to update order status: {e}"}
