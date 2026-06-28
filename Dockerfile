FROM python:3.12-slim

# Install cloudflared (Cloudflare Tunnel daemon) alongside the Python app.
# Combining two long-running processes in one image is a deliberate
# trade-off for shippability — see note below about the docker-compose
# alternative if you'd rather keep them as separate, independently
# restartable containers.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
        -o /usr/local/bin/cloudflared \
    && chmod +x /usr/local/bin/cloudflared \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bulkclix_mcp.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

# Run as non-root.
RUN useradd -m -u 1000 mcpuser && chown -R mcpuser:mcpuser /app
USER mcpuser

# Optional: only useful for local debugging via `-p 8000:8000`.
# Once the tunnel is wired up, the container never needs an inbound
# port published — cloudflared dials OUT to Cloudflare's edge, which
# is the whole point: no open inbound ports, no public IP required.
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]