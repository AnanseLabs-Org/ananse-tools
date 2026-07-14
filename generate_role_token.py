#!/usr/bin/env python3
import os
import sys
import jwt as pyjwt

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate_role_token.py <role> [secret]")
        print("Roles: user, admin")
        sys.exit(1)

    role = sys.argv[1].lower()
    if role not in ("user", "admin"):
        print(f"Error: Unknown role '{role}'. Valid roles are: user, admin")
        sys.exit(1)

    secret = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("MCP_ROLE_TOKEN_SECRET")
    if not secret:
        print("Error: MCP_ROLE_TOKEN_SECRET not found in environment and not passed as argument.")
        sys.exit(1)

    payload = {"role": role}
    token = pyjwt.encode(payload, secret, algorithm="HS256")
    print(f"Role: {role}")
    print(f"X-API-Key: {token}")

if __name__ == "__main__":
    main()
