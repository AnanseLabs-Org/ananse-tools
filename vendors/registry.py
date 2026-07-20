from typing import Any, Dict, Optional, List
from db import _get_db
from middleware import _get_caller_roles
from vendors.provider import (
    BaseVendorProvider,
    HttpVendorProvider,
    TelecomVendorProvider,
    ShopifyVendorProvider
)

STATIC_VENDORS_LIST = [
    {
        "vendor_id": "234490c6-09e1-4125-b9cd-506d64eb2c50",
        "name": "Horlap",
        "categories": ["restaurant", "food_delivery", "food"],
        "order_types": ["inhouse"],
        "menu_url": "https://api.horlap.com/api/menu/",
        "order_url": "https://api.horlap.com/api/orders/create-and-initiate-payment/",
        "payment_methods": ["momo"],
        "vendor_type": "external_api"
    },
    {
        "vendor_id": "f5f0b5aa-399a-4c28-98b7-6b6f3ff8cfa0",
        "name": "MTN Airtime & Data",
        "categories": ["airtime", "data", "topup", "bundles"],
        "vendor_type": "internal_service",
        "service": "telecom",
        "network": "MTN",
        "payment_methods": ["momo"]
    },
    {
        "vendor_id": "a90b4cc5-5c12-4217-bfd2-c76a54f0a99c",
        "name": "Telecel Airtime & Data",
        "categories": ["airtime", "data", "topup", "bundles"],
        "vendor_type": "internal_service",
        "service": "telecom",
        "network": "TELECEL",
        "payment_methods": ["momo"]
    },
    {
        "vendor_id": "d02fa3c5-92a0-410a-8bf7-e16fa5cfc99b",
        "name": "AirtelTigo Airtime & Data",
        "categories": ["airtime", "data", "topup", "bundles"],
        "vendor_type": "internal_service",
        "service": "telecom",
        "network": "AIRTELTIGO",
        "payment_methods": ["momo"]
    }
]

_INTERNAL_ONLY_FIELDS = {"menu_url", "order_url"}


def _public_vendor_view(vendor: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal-only fields (API endpoints) before exposing to the model."""
    return {k: v for k, v in vendor.items() if k not in _INTERNAL_ONLY_FIELDS}


def _expand_category_query(query: str) -> set[str]:
    """Expand category query with synonyms to improve discoverability."""
    synonyms = {
        "food": {"restaurant", "dining", "takeout", "delivery", "eatery", "cafe", "fast food", "dishes", "meals"},
        "restaurant": {"food", "dining", "eatery", "cafe", "fast food", "meals"},
        "dining": {"food", "restaurant", "eatery"},
        "delivery": {"takeout", "food", "restaurant"},
        "takeout": {"delivery", "food", "restaurant"},
    }
    q = query.lower().strip()
    expanded = {q}
    for key, syn_set in synonyms.items():
        if q == key or q in syn_set:
            expanded.add(key)
            expanded.update(syn_set)
    return expanded


def _filter_vendors_by_roles(vendors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filters the list of vendors based on the Keycloak client roles of the caller.
    Roles with prefix 'vendor:' specify the allowed vendor_id.
    """
    roles = _get_caller_roles()
    if not roles or "admin" in roles:
        return vendors

    vendor_role_ids = set()
    has_vendor_restrict = False
    for r in roles:
        if r.startswith("vendor:"):
            has_vendor_restrict = True
            vendor_role_ids.add(r[len("vendor:"):])

    if not has_vendor_restrict:
        return vendors

    return [v for v in vendors if v.get("vendor_id") in vendor_role_ids or v.get("name") in vendor_role_ids]


async def seed_vendors_if_empty(db) -> None:
    """Helper to seed STATIC_VENDORS_LIST if the vendors collection is empty."""
    count = await db.vendors.count_documents({})
    if count == 0:
        await db.vendors.insert_many(STATIC_VENDORS_LIST)


async def get_all_vendors() -> List[Dict[str, Any]]:
    """Fetch all vendors from MongoDB, seeding first if empty, and filtering by roles."""
    db = _get_db()
    if db is None:
        return _filter_vendors_by_roles(STATIC_VENDORS_LIST)
    await seed_vendors_if_empty(db)
    cursor = db.vendors.find({}, {"_id": 0})
    vendors = await cursor.to_list(length=100)
    return _filter_vendors_by_roles(vendors)


async def _lookup_vendor(vendor_id: str) -> Optional[Dict[str, Any]]:
    """Internal lookup returning the FULL vendor record from MongoDB, filtered by roles."""
    db = _get_db()
    if db is None:
        vendors = _filter_vendors_by_roles(STATIC_VENDORS_LIST)
        return next((v for v in vendors if v["vendor_id"] == vendor_id), None)
    
    await seed_vendors_if_empty(db)
    vendor_data = await db.vendors.find_one({"vendor_id": vendor_id}, {"_id": 0})
    if not vendor_data:
        return None
        
    filtered = _filter_vendors_by_roles([vendor_data])
    return filtered[0] if filtered else None


async def get_vendor_provider(vendor_id: str) -> Optional[BaseVendorProvider]:
    """
    Look up vendor metadata and secure credentials, then instantiate the correct provider.
    """
    vendor_data = await _lookup_vendor(vendor_id)
    if not vendor_data:
        return None

    db = _get_db()
    credentials = None
    if db is not None:
        credentials = await db.shopify_credentials.find_one({"vendor_id": vendor_id}, {"_id": 0})

    v_type = vendor_data.get("vendor_type")
    if v_type == "shopify":
        return ShopifyVendorProvider(vendor_data, credentials)
    elif v_type == "internal_service":
        return TelecomVendorProvider(vendor_data, credentials)
    else:
        # Defaults to HttpVendorProvider
        return HttpVendorProvider(vendor_data, credentials)
