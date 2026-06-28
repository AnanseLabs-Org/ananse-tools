#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
  echo "ERROR: CLOUDFLARE_TUNNEL_TOKEN is not set. Get this from the Cloudflare" >&2
  echo "Zero Trust dashboard: Networks > Tunnels > your tunnel > install connector." >&2
  exit 1
fi

if [[ -z "${BULKCLIX_API_KEY:-}" ]]; then
  echo "ERROR: BULKCLIX_API_KEY is not set." >&2
  exit 1
fi

# Start the MCP server (SSE transport) in the background.
python server.py sse &
MCP_PID=$!

# Start cloudflared in the background too, tunneling to the local MCP
# server. Inside the same container, "localhost:8000" reaches the
# Python process directly — no Docker networking config needed.
# The ingress rule (public hostname -> http://localhost:8000) is
# configured in the Cloudflare dashboard for this tunnel, not here.
cloudflared tunnel run --token "${CLOUDFLARE_TUNNEL_TOKEN}" &
TUNNEL_PID=$!

# If either process dies, kill the other and exit non-zero so the
# container reports failure clearly instead of limping along with
# only one half of the pair still running.
wait -n "$MCP_PID" "$TUNNEL_PID"
EXIT_CODE=$?
kill "$MCP_PID" "$TUNNEL_PID" 2>/dev/null || true
exit "$EXIT_CODE"