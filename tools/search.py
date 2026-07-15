import os
import math
import httpx
from typing import List, Dict, Any, Optional
from vendors.registry import STATIC_VENDORS_LIST, _lookup_vendor, _public_vendor_view
from http_client import _call_vendor_api
from vendors.menu import _flatten_menu

# Local Ollama configuration
OLLAMA_API_BASE = os.environ.get("OLLAMA_API_BASE", "http://ollama:11434")
OLLAMA_EMBED_URL = f"{OLLAMA_API_BASE}/api/embed"
OLLAMA_PULL_URL = f"{OLLAMA_API_BASE}/api/pull"
MODEL_NAME = "all-minilm:l6-v2"

# In-memory index cache
_SEMANTIC_INDEX: List[Dict[str, Any]] = []
_INDEX_LOADED = False

async def _ensure_model_exists(client: httpx.AsyncClient):
    """Checks if the all-minilm:l6-v2 model is pulled, otherwise downloads it."""
    try:
        # Try a dummy embedding first
        res = await client.post(
            OLLAMA_EMBED_URL,
            json={"model": MODEL_NAME, "input": ["test"]},
            timeout=3.0
        )
        if res.status_code == 200:
            return
    except Exception:
        pass
        
    print(f"Ollama model {MODEL_NAME!r} not found. Pulling model...", flush=True)
    try:
        res = await client.post(
            OLLAMA_PULL_URL,
            json={"name": MODEL_NAME, "stream": False},
            timeout=180.0
        )
        if res.status_code == 200:
            print(f"Successfully pulled Ollama model {MODEL_NAME!r}!", flush=True)
        else:
            print(f"Error pulling model: {res.text}", flush=True)
    except Exception as e:
        print(f"Failed to pull model via API: {e}", flush=True)

async def _get_embeddings(texts: List[str]) -> List[List[float]]:
    """Helper to fetch embeddings for a list of texts using local Ollama."""
    if not texts:
        return []
        
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Make sure model is pulled
        await _ensure_model_exists(client)
        
        response = await client.post(
            OLLAMA_EMBED_URL,
            json={"model": MODEL_NAME, "input": texts}
        )
        if response.status_code != 200:
            raise RuntimeError(f"Ollama API error ({response.status_code}): {response.text}")
            
        data = response.json()
        return data.get("embeddings", [])

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors in pure Python."""
    if len(a) != len(b) or not a:
        return 0.0
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))

async def rebuild_semantic_index() -> int:
    """Fetches all items from all active food vendors and builds the vector embedding cache."""
    global _SEMANTIC_INDEX, _INDEX_LOADED
    
    new_index = []
    
    # 1. Gather all food vendors
    food_vendors = [v for v in STATIC_VENDORS_LIST if v.get("vendor_type") == "food_merchant"]
    
    # 2. Gather all menu items
    all_items = []
    for vendor in food_vendors:
        v_id = vendor["vendor_id"]
        v_name = vendor["name"]
        
        try:
            raw_response = await _call_vendor_api("GET", vendor["menu_url"])
            if isinstance(raw_response, list):
                items = _flatten_menu(raw_response)
                for item in items:
                    item["vendor_id"] = v_id
                    item["vendor_name"] = v_name
                    all_items.append(item)
        except Exception as e:
            print(f"Warning: Failed to fetch menu for {v_name}: {e}")
            continue

    if not all_items:
        _SEMANTIC_INDEX = []
        _INDEX_LOADED = True
        return 0

    # 3. Create description texts to embed (name + description if available)
    texts_to_embed = []
    for item in all_items:
        desc = item.get("description", "") or ""
        text = f"{item['name']}. {desc}".strip()
        texts_to_embed.append(text)

    # 4. Generate embeddings in batches of 32 to avoid API payload limits
    batch_size = 32
    embeddings = []
    for i in range(0, len(texts_to_embed), batch_size):
        batch = texts_to_embed[i:i + batch_size]
        try:
            batch_embeddings = await _get_embeddings(batch)
            embeddings.extend(batch_embeddings)
        except Exception as e:
            print(f"Error fetching embeddings batch: {e}")
            embeddings.extend([[0.0] * 384] * len(batch))

    # 5. Populate the semantic index
    for item, vector in zip(all_items, embeddings):
        item["vector"] = vector
        new_index.append(item)

    _SEMANTIC_INDEX = new_index
    _INDEX_LOADED = True
    return len(new_index)

from mcp.types import ToolAnnotations
from app import general as mcp
from middleware import _get_caller_roles

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def search(
    *,
    query: str,
    vendor_id: Any = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    """
    Search for vendors (merchants), menu items, and MCP tools/capabilities semantically in a single query.
    Use this to resolve which tool to call, which vendor fits a concept, or what food/goods are available.
    """
    global _INDEX_LOADED
    
    # 1. Ensure menu index is loaded
    if not _INDEX_LOADED:
        await rebuild_semantic_index()
        
    # 2. Get a single query embedding (one network round-trip to Ollama!)
    try:
        query_embeddings = await _get_embeddings([query])
        query_vector = query_embeddings[0]
    except Exception as e:
        print(f"Embedding search query failed: {e}")
        return {
            "success": False,
            "error": f"Failed to compute query embedding: {e}"
        }

    # 3. Resolve user role to filter results
    caller_roles = _get_caller_roles()

    # --- DOMAIN A: MCP Tools ---
    matched_tools = []
    try:
        import inspect
        from app import mcp as root_mcp
        all_tools = []
        for p in root_mcp.providers:
            try:
                res = p.list_tools()
                if inspect.iscoroutine(res):
                    tools = await res
                else:
                    tools = res
            except Exception:
                continue

            for tool in tools:
                name = getattr(tool, "name", "")
                if name == "search":
                    continue
                
                # Enforce security role check on search results
                tags = getattr(tool, "tags", None) or set()
                if "admin" not in caller_roles and "admin" in tags:
                    continue

                desc = getattr(tool, "description", "") or ""
                all_tools.append({
                    "name": name,
                    "description": desc.strip()
                })
                
        if all_tools:
            tool_texts = [f"{t['name']}: {t['description']}" for t in all_tools]
            tool_embeddings = await _get_embeddings(tool_texts)
            for tool, vec in zip(all_tools, tool_embeddings):
                similarity = _cosine_similarity(query_vector, vec)
                if similarity > 0.25:
                    tool_copy = dict(tool)
                    tool_copy["similarity"] = round(similarity, 4)
                    matched_tools.append(tool_copy)
            matched_tools.sort(key=lambda x: x["similarity"], reverse=True)
    except Exception as e:
        print(f"Error matching tools semantically: {e}")

    # --- DOMAIN B: Vendors ---
    matched_vendors = []
    try:
        vendor_texts = []
        for v in STATIC_VENDORS_LIST:
            cats = ", ".join(v.get("categories", []))
            desc = v.get("description", "") or v.get("notes", "") or ""
            text = f"{v['name']} ({cats}). {desc}".strip()
            vendor_texts.append(text)
            
        if vendor_texts:
            vendor_embeddings = await _get_embeddings(vendor_texts)
            for v, vec in zip(STATIC_VENDORS_LIST, vendor_embeddings):
                similarity = _cosine_similarity(query_vector, vec)
                if similarity > 0.30:
                    v_copy = _public_vendor_view(v)
                    v_copy["similarity"] = round(similarity, 4)
                    matched_vendors.append(v_copy)
            matched_vendors.sort(key=lambda x: x["similarity"], reverse=True)
    except Exception as e:
        print(f"Error matching vendors semantically: {e}")

    # --- DOMAIN C: Menu Items ---
    matched_items = []
    try:
        for item in _SEMANTIC_INDEX:
            if vendor_id and item["vendor_id"] != vendor_id:
                continue
            vector = item.get("vector")
            if not vector or all(v == 0.0 for v in vector):
                continue
            similarity = _cosine_similarity(query_vector, vector)
            if similarity > 0.30:
                item_copy = dict(item)
                item_copy.pop("vector", None)
                item_copy["similarity"] = round(similarity, 4)
                matched_items.append(item_copy)
        matched_items.sort(key=lambda x: x["similarity"], reverse=True)
    except Exception as e:
        print(f"Error matching menu items semantically: {e}")

    return {
        "success": True,
        "query": query,
        "tools": matched_tools[:top_n],
        "vendors": matched_vendors[:top_n],
        "menu_items": matched_items[:top_n]
    }
