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
      - /Users/fiifinketia/vztd.xyz/ananselabs/bulkclix-mcp-python
      - server.py
    type: stdio
```

### Option 2: HTTP / SSE transport (Remote/Streamable)

Run the server on a port (e.g. port `8000`):

```bash
uv run server.py sse
```

Then configure LibreChat to use the SSE endpoint:

```yaml
mcpServers:
  bulkclix:
    url: http://localhost:8000/sse
    type: sse
```

---

## License

MIT © AnanseLabs
