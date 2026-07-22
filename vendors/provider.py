import httpx
import logging
from typing import Any, Dict, List, Optional
from http_client import _call_vendor_api
from vendors.menu import _flatten_menu

logger = logging.getLogger("mcp-shopify-provider")

class BaseVendorProvider:
    def __init__(self, vendor_data: Dict[str, Any], credentials: Optional[Dict[str, Any]] = None):
        self.vendor_data = vendor_data
        self.credentials = credentials or {}
        self.vendor_id = vendor_data["vendor_id"]
        self.name = vendor_data["name"]
        self.categories = vendor_data.get("categories", [])
        self.vendor_type = vendor_data.get("vendor_type")

    async def get_menu(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def create_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    async def get_collections(self) -> List[Dict[str, Any]]:
        return []

    async def get_metafields(self, owner_resource: str, owner_id: str) -> List[Dict[str, Any]]:
        return []

    async def get_customer(self, customer_id: str) -> Dict[str, Any]:
        return {}

    async def get_orders(self) -> List[Dict[str, Any]]:
        return []


class HttpVendorProvider(BaseVendorProvider):
    async def get_menu(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        menu_url = self.vendor_data.get("menu_url")
        if not menu_url:
            return []
        raw_response = await _call_vendor_api("GET", menu_url)
        if not isinstance(raw_response, list):
            return []
        items = _flatten_menu(raw_response)
        if query:
            q = query.lower()
            items = [i for i in items if q in (i["name"] or "").lower()]
        return items

    async def create_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        order_url = self.vendor_data.get("order_url")
        if not order_url:
            return {"success": False, "error": "No configured order url"}
        return await _call_vendor_api("POST", order_url, json=payload)


class TelecomVendorProvider(BaseVendorProvider):
    async def get_menu(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        # Telecom has no catalog menu in this sense
        return []

    async def create_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "Use dedicated airtime/data purchase tools directly."}


class ShopifyVendorProvider(BaseVendorProvider):
    def __init__(self, vendor_data: Dict[str, Any], credentials: Optional[Dict[str, Any]] = None):
        super().__init__(vendor_data, credentials)
        self.shop_name = self.credentials.get("shop_name") or ""
        self.admin_token = self.credentials.get("admin_access_token") or ""
        self.storefront_token = self.credentials.get("storefront_access_token") or ""
        self.api_version = "2024-07"

    @property
    def admin_base_url(self) -> str:
        if "." in self.shop_name:
            return f"https://{self.shop_name}/admin/api/{self.api_version}"
        return f"https://{self.shop_name}.myshopify.com/admin/api/{self.api_version}"

    @property
    def storefront_url(self) -> str:
        if "." in self.shop_name:
            return f"https://{self.shop_name}/api/{self.api_version}/graphql.json"
        return f"https://{self.shop_name}.myshopify.com/api/{self.api_version}/graphql.json"

    async def _graphql_storefront(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Storefront-Access-Token": self.storefront_token
        }
        logger.info(f"Shopify Storefront request to URL: {self.storefront_url} with query:\n{query}")
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                resp = await client.post(self.storefront_url, json={"query": query, "variables": variables}, headers=headers)
                logger.info(f"Shopify Storefront response received with status code: {resp.status_code}")
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Shopify Storefront products fetch failed: {e}")
            raise

    async def _admin_request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.admin_token
        }
        url = f"{self.admin_base_url}/{path.lstrip('/')}"
        logger.info(f"Shopify Admin request {method} to URL: {url}")
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                resp = await client.request(method, url, headers=headers, **kwargs)
                logger.info(f"Shopify Admin response received with status code: {resp.status_code}")
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Shopify Admin request failed: {e}")
            raise

    async def get_menu(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        # Fetch products via Storefront API and map them to dish format
        gql = """
        query GetProducts($first: Int) {
          products(first: $first) {
            edges {
              node {
                id
                title
                description
                availableForSale
                images(first: 1) {
                  edges {
                    node {
                      url
                    }
                  }
                }
                variants(first: 10) {
                  edges {
                    node {
                      id
                      title
                      price {
                        amount
                      }
                      availableForSale
                    }
                  }
                }
              }
            }
          }
        }
        """
        try:
            res = await self._graphql_storefront(gql, {"first": 100})
            products = res.get("data", {}).get("products", {}).get("edges", [])
            items = []
            for p in products:
                node = p.get("node", {})
                prod_id = node.get("id")
                title = node.get("title")
                desc = node.get("description")
                images = node.get("images", {}).get("edges", [])
                image_url = images[0]["node"]["url"] if images else None
                variants = node.get("variants", {}).get("edges", [])
                
                # If single variant, flatten
                if len(variants) <= 1:
                    price = float(variants[0]["node"]["price"]["amount"]) if variants else 0.0
                    items.append({
                        "dish_id": prod_id, # Can be string ID for Shopify
                        "name": title,
                        "description": desc,
                        "price": price,
                        "image_url": image_url,
                        "is_available": node.get("availableForSale", False),
                        "category": "Shopify Product",
                        "addons": []
                    })
                else:
                    # Multiple variants as addons/options
                    price = float(variants[0]["node"]["price"]["amount"]) if variants else 0.0
                    addons = []
                    for v in variants[1:]:
                        v_node = v.get("node", {})
                        addons.append({
                            "addon_id": v_node.get("id"),
                            "name": v_node.get("title"),
                            "price": float(v_node["price"]["amount"]),
                            "is_active": v_node.get("availableForSale", False)
                        })
                    items.append({
                        "dish_id": prod_id,
                        "name": title,
                        "description": desc,
                        "price": price,
                        "image_url": image_url,
                        "is_available": node.get("availableForSale", False),
                        "category": "Shopify Product",
                        "addons": addons
                    })
            if query:
                q = query.lower()
                items = [i for i in items if q in (i["name"] or "").lower()]
            return items
        except Exception as e:
            print(f"Shopify Storefront products fetch failed: {e}")
            return []

    async def create_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Formulate Shopify Order structure from the payload and create via Admin API
        # Mark as paid in financial_status
        items = payload.get("items", [])
        line_items = []
        for it in items:
            line_items.append({
                "variant_id": it.get("variant_id") or it.get("dish_id"),
                "quantity": it.get("quantity", 1)
            })
            
        shopify_payload = {
            "order": {
                "line_items": line_items,
                "financial_status": "paid",
                "phone": payload.get("payment_number"),
                "note": f"Paid via MoMo on BulkClix. Net: {payload.get('network')}"
            }
        }
        
        # Add shipping address if delivery
        if payload.get("order_type") == "delivery":
            shopify_payload["order"]["shipping_address"] = {
                "address1": payload.get("delivery_address"),
                "first_name": payload.get("customer_name", "Valued"),
                "last_name": "Customer"
            }
            
        try:
            res = await self._admin_request("POST", "orders.json", json=shopify_payload)
            order_id = res.get("order", {}).get("id")
            return {
                "success": True,
                "order_id": str(order_id),
                "shopify_order": res.get("order")
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to create Shopify order: {e}"}

    async def get_collections(self) -> List[Dict[str, Any]]:
        # Fetch collections using Storefront API
        gql = """
        query {
          collections(first: 50) {
            edges {
              node {
                id
                title
                description
              }
            }
          }
        }
        """
        try:
            res = await self._graphql_storefront(gql)
            edges = res.get("data", {}).get("collections", {}).get("edges", [])
            return [e.get("node", {}) for e in edges]
        except Exception as e:
            print(f"Shopify collections fetch failed: {e}")
            return []

    async def get_metafields(self, owner_resource: str, owner_id: str) -> List[Dict[str, Any]]:
        # Admin GraphQL API or Admin REST API metafields
        # Let's query metafields via Admin REST API: /admin/api/{version}/{resource_type}/{resource_id}/metafields.json
        try:
            path = f"{owner_resource}/{owner_id}/metafields.json"
            res = await self._admin_request("GET", path)
            return res.get("metafields", [])
        except Exception as e:
            print(f"Shopify metafields query failed: {e}")
            return []

    async def get_customer(self, customer_id: str) -> Dict[str, Any]:
        try:
            res = await self._admin_request("GET", f"customers/{customer_id}.json")
            return res.get("customer", {})
        except Exception as e:
            print(f"Shopify customer query failed: {e}")
            return {}

    async def get_orders(self) -> List[Dict[str, Any]]:
        try:
            res = await self._admin_request("GET", "orders.json")
            return res.get("orders", [])
        except Exception as e:
            print(f"Shopify orders query failed: {e}")
            return []
