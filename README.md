# BulkClix MCP Server (Python FastMCP)

A Python-based **MCP (Model Context Protocol) server** that gives AI agents (LibreChat, Claude Desktop, Cursor, etc.) full access to the [BulkClix](https://bulkclix.com) platform via natural language.

Developed with **FastMCP** for simple tool declarations.

---

## Features

- **SMS**: Send bulk SMS, fetch campaign reports, request/list Sender IDs.
- **OTP**: Send and verify OTPs via SMS and Email.
- **Airtime**: List networks, purchase airtime via momo, and send airtime from wallet balance.
- **Mobile Money**: MoMo payment collections, status checks, disbursements.
- **Bank Transfer**: Disburse to bank accounts, list banks.
- **Data Bundles**: Fetch bundles, purchase data packages.
- **KYC**: MSISDN owner name lookups.
- **Contacts**: Full CRUD for contact groups & contacts.
- **Account**: Check wallet balance.

---

## Installation & Running

Using `uv` is highly recommended as it automatically manages dependencies:

```bash
# Run server using uv
uv run server.py
```

If you want the server to use a default BulkClix key, set `BULKCLIX_API_KEY` before starting it:

```bash
export BULKCLIX_API_KEY="your-bulkclix-api-key"
uv run server.py mcp
```

To expose admin-only workflows like contact management, enable internal tools on the server:

```bash
export BULKCLIX_ENABLE_INTERNAL_TOOLS=true
```

The public chat-facing tools now work without caller-supplied keys.
SMS and OTP tools automatically pick the first sender ID returned by BulkClix.
Airtime and data purchases first collect payment through MoMo, then complete the fulfillment after payment is confirmed.

---

## Configuration in LibreChat

### Option 1: stdio transport (default)

Add this under `mcpServers` in your `librechat.yaml`:

```yaml
mcpServers:
  bulkclix:
    command: uv
    args:
      - run
      - --directory
      - /path/to/bulkclix-mcp
      - server.py
    type: stdio
```

### Option 2: HTTP / MCP transport (Remote/Streamable)

Run the server on a port (e.g. port `8000`):

```bash
cd bulkclix-mcp
uv run server.py mcp
```

Then configure LibreChat to use the MCP-over-HTTP endpoint:

```yaml
mcpServers:
  bulkclix:
    url: http://localhost:8000/sse
    type: sse
```

You can then tunnel that port with `localtunnel`:

```bash
npx localtunnel --port 8000
```

If `BULKCLIX_API_KEY` is set on the machine running the server, the client can use the public tools without providing any per-call key.
Admin-only tools are hidden unless `BULKCLIX_ENABLE_INTERNAL_TOOLS=true` is set on the server.

---

## License

MIT © AnanseLabs
