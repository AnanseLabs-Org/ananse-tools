FROM kalilinux/kali-rolling

# ── System packages ─────────────────────────────────────────────────────────
# Python3, pip, sudo, and all Kali pentest CLI tools exposed by the server.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-setuptools python3-wheel \
        python3-pydantic python3-yaml python3-dotenv python3-click python3-httpx python3-rich \
        sudo \
        nmap gobuster nikto sqlmap hydra dirb \
        exploitdb metasploit-framework \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the kali_server package.
# Build context is now the ananselabs/ monorepo root (set in docker-compose),
# so we copy only the server source here.
COPY tools/servers/kali_server/ .
RUN pip install --no-cache-dir --break-system-packages .

# ── Bake skills into the image ───────────────────────────────────────────────
# Copy the entire skills library from the monorepo into /app/skills so they
# are available without a volume mount. A volume mount can still override this
# at runtime for local development.
RUN mkdir -p /app/skills
COPY skills/skills/ /app/skills/

# Create the standard wordlist directory structure and symlink to the installed dirb wordlist
RUN mkdir -p /usr/share/wordlists/dirb && ln -sf /usr/share/dirb/wordlists/common.txt /usr/share/wordlists/dirb/common.txt

# ── Non-root user with passwordless sudo ─────────────────────────────────────
# nmap needs raw sockets (CAP_NET_RAW) for SYN scans — sudo is the escape hatch.
RUN useradd -m -u 1000 kaliuser \
    && echo "kaliuser ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/kaliuser \
    && chmod 0440 /etc/sudoers.d/kaliuser

USER kaliuser

# Port 8001 — default for kali-server-mcp HTTP transport.
EXPOSE 8001

# Bind to 0.0.0.0 so Docker networking reaches it from other containers.
# The port is NOT published to the host (internal network only).
ENTRYPOINT ["kali-server-mcp", "--ip", "0.0.0.0", "--port", "8001"]
