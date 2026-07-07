import os
import re
import json
import logging
import httpx
from fastmcp import FastMCP
from app import general as mcp

logger = logging.getLogger("mcp-openwa")

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")
RULES_FILE = os.path.join(CONFIG_DIR, "openwa_rules.json")
CACHE_FILE = os.path.join(CONFIG_DIR, "openwa_schema_cache.json")

# Default OpenWA service URL inside the Docker network
OPENWA_SERVICE_URL = os.environ.get("OPENWA_SERVICE_URL", "http://openwa-api:2785")
OPENWA_DOCS_JSON_URL = f"{OPENWA_SERVICE_URL}/api/docs-json"

def load_rules():
    """Load route filtering rules from the config file."""
    if not os.path.exists(RULES_FILE):
        logger.warning(f"Rules file not found at {RULES_FILE}, exposing all tools.")
        return []
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("rules", [])
    except Exception as e:
        logger.error(f"Failed to load rules: {e}")
        return []

def filter_openapi_spec(spec, rules):
    """Filter OpenAPI paths based on the regex patterns defined in rules."""
    if not rules:
        return spec

    filtered_paths = {}
    original_paths = spec.get("paths", {})

    compiled_rules = []
    for rule in rules:
        try:
            pattern = re.compile(rule["pattern"])
            compiled_rules.append((pattern, rule.get("type", "public")))
        except Exception as e:
            logger.error(f"Invalid regex pattern '{rule.get('pattern')}': {e}")

    for path, path_item in original_paths.items():
        matched = False
        for pattern, rule_type in compiled_rules:
            if pattern.match(path):
                matched = True
                break
        if matched:
            filtered_paths[path] = path_item
            logger.debug(f"Exposing OpenWA path: {path}")
        else:
            logger.debug(f"Filtering out OpenWA path: {path}")

    filtered_spec = dict(spec)
    filtered_spec["paths"] = filtered_paths
    return filtered_spec

def fetch_schema_sync() -> dict | None:
    """Fetch the OpenAPI schema synchronously with a short timeout."""
    try:
        logger.info(f"Attempting to fetch OpenWA schema from {OPENWA_DOCS_JSON_URL}...")
        # Synchronous request at import/startup time
        with httpx.Client(timeout=3.0) as client:
            response = client.get(OPENWA_DOCS_JSON_URL)
            if response.status_code == 200:
                schema = response.json()
                # Save to cache
                os.makedirs(CONFIG_DIR, exist_ok=True)
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(schema, f, indent=2)
                logger.info(f"Successfully fetched and cached OpenWA schema.")
                return schema
            else:
                logger.warning(f"Failed to fetch schema: HTTP {response.status_code}")
    except Exception as e:
        logger.warning(f"Could not connect to OpenWA container to fetch schema: {e}")
    return None

def load_cached_schema() -> dict | None:
    """Load the OpenAPI schema from the local cache file."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                schema = json.load(f)
                logger.info(f"Loaded OpenWA schema from local cache at {CACHE_FILE}")
                return schema
        except Exception as e:
            logger.error(f"Failed to read cached schema: {e}")
    return None

def initialize_openwa_mcp():
    """Build the child FastMCP server and mount it on the parent."""
    # 1. Fetch or load cached schema
    schema = fetch_schema_sync()
    if not schema:
        schema = load_cached_schema()

    if not schema:
        logger.error("No OpenWA schema available (network fetch failed and no cache exists). Skipping OpenWA registration.")
        return

    # 2. Filter paths based on rules
    rules = load_rules()
    filtered_schema = filter_openapi_spec(schema, rules)

    # 3. Configure authentication headers and httpx client
    master_key = os.environ.get("API_MASTER_KEY", "")
    headers = {}
    if master_key:
        # OpenWA supports both X-API-Key and Authorization Bearer header
        headers["X-API-Key"] = master_key
        logger.info("API_MASTER_KEY configured; injecting X-API-Key auth header.")
    else:
        logger.warning("No API_MASTER_KEY found in environment. OpenWA requests might be unauthenticated.")

    # Rewrite servers list in OpenAPI spec to point to the docker container URL
    filtered_schema["servers"] = [{"url": OPENWA_SERVICE_URL}]

    # Create the HTTP client with the correct base URL and authorization headers
    async_client = httpx.AsyncClient(
        base_url=OPENWA_SERVICE_URL,
        headers=headers,
        timeout=30.0
    )

    try:
        # 4. Generate the FastMCP server from the OpenAPI schema
        openwa_server = FastMCP.from_openapi(
            openapi_spec=filtered_schema,
            client=async_client,
            name="openwa",
            validate_output=False  # Disable strict output validation to handle dynamic responses cleanly
        )

        # 5. Mount the child server on our main app server
        mcp.mount(openwa_server)
        logger.info("Successfully mounted OpenWA MCP tools.")
    except Exception as e:
        logger.error(f"Failed to create and mount OpenWA FastMCP server: {e}")

# Trigger registration on import
initialize_openwa_mcp()
