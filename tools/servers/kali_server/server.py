"""
Kali Computer Server — server.py
=================================
FastMCP HTTP Server that wraps Kali Linux CLI tools (nmap, gobuster, nikto, sqlmap,
hydra, searchsploit, msfconsole) and exposes them as MCP tools. Also serves the
shared Ananse skills library from /root/ananselabs/skills via SkillsDirectoryProvider.

Runs on Streamable HTTP transport, port 8001.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
from typing import Any, Dict
import fastmcp
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP application
# ---------------------------------------------------------------------------

import os
from pathlib import Path
from fastmcp.server.providers.skills import SkillsDirectoryProvider

fastmcp.settings.sse_path = "/mcp"
fastmcp.settings.message_path = "/messages/"
# Disable DNS rebinding checks on local internal container communication to avoid 421 Misdirected Request errors
fastmcp.settings.http_host_origin_protection = False

mcp = FastMCP("kali-server")

# Skills are mounted at /root/ananselabs/skills inside the container.
# SKILLS_DIR env var overrides the default (set in docker-compose).
# supporting_files="resources" makes every file in every skill individually
# enumerable via list_resources() — no manifest round-trip required.
skills_path = Path(os.environ.get("SKILLS_DIR", "/root/ananselabs/skills"))
skills_path.mkdir(parents=True, exist_ok=True)
mcp.add_provider(
    SkillsDirectoryProvider(
        roots=skills_path,
        reload=True,
        supporting_files="resources",
    )
)

def _run(cmd: list[str], timeout: int = 300) -> dict[str, Any]:
    """Execute *cmd* as a subprocess and return a structured result dict."""
    log.debug("Running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "command": " ".join(cmd),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": " ".join(cmd),
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds.",
        }
    except FileNotFoundError as exc:
        return {
            "command": " ".join(cmd),
            "returncode": -1,
            "stdout": "",
            "stderr": f"Tool not found: {exc}. Ensure it is installed in the container.",
        }


# ── nmap ────────────────────────────────────────────────────────────────────

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def nmap(
    *,
    target: str,
    scan_type: str = "-sV",
    ports: str = "",
    additional_args: str = "",
) -> Dict[str, Any]:
    """
    Run nmap against one or more targets for network discovery and port scanning.

    :param target: IP address, hostname, or CIDR range.
    :param scan_type: nmap scan flags (default "-sV").
    :param ports: Port spec (e.g. "22,80,443").
    :param additional_args: Extra nmap flags.
    """
    cmd = ["sudo", "nmap"] + scan_type.split()
    if ports:
        cmd += ["-p", ports]
    if additional_args:
        cmd += additional_args.split()
    cmd.append(target)
    return _run(cmd)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def gobuster(
    *,
    url: str,
    mode: str = "dir",
    wordlist: str = "/usr/share/wordlists/dirb/common.txt",
    additional_args: str = "",
) -> Dict[str, Any]:
    """
    Run gobuster to brute-force URIs, DNS subdomains, or virtual host names.

    :param url: Target URL.
    :param mode: "dir", "dns", or "vhost".
    :param wordlist: Path to wordlist inside the container.
    :param additional_args: Extra gobuster flags.
    """
    cmd = ["gobuster", mode, "-u", url, "-w", wordlist]
    if additional_args:
        cmd += additional_args.split()
    return _run(cmd)


# ── nikto ───────────────────────────────────────────────────────────────────

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def nikto(
    *,
    target: str,
    additional_args: str = "",
) -> Dict[str, Any]:
    """
    Run Nikto web server scanner to identify vulnerabilities and misconfigurations.

    :param target: Host or URL.
    :param additional_args: Extra Nikto options.
    """
    cmd = ["nikto", "-h", target]
    if additional_args:
        cmd += additional_args.split()
    return _run(cmd)


# ── sqlmap ──────────────────────────────────────────────────────────────────

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def sqlmap(
    *,
    url: str,
    data: str = "",
    additional_args: str = "",
) -> Dict[str, Any]:
    """
    Run sqlmap to detect and exploit SQL injection vulnerabilities.

    :param url: Target URL with query params.
    :param data: POST data for form testing.
    :param additional_args: Extra sqlmap flags.
    """
    cmd = ["sqlmap", "-u", url, "--batch"]
    if data:
        cmd += ["--data", data]
    if additional_args:
        cmd += additional_args.split()
    return _run(cmd)


# ── hydra ───────────────────────────────────────────────────────────────────

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def hydra(
    *,
    target: str,
    service: str,
    username: str = "",
    username_file: str = "",
    password: str = "",
    password_file: str = "",
    additional_args: str = "",
) -> Dict[str, Any]:
    """
    Run Hydra for online password brute-forcing against network services.

    :param target: Target IP or hostname.
    :param service: Network service.
    :param username: Single username.
    :param username_file: Path to usernames file.
    :param password: Single password.
    :param password_file: Path to passwords file.
    :param additional_args: Extra Hydra flags.
    """
    cmd = ["hydra"]
    cmd += ["-l", username] if username else ["-L", username_file]
    cmd += ["-p", password] if password else ["-P", password_file]
    if additional_args:
        cmd += additional_args.split()
    cmd += [target, service]
    return _run(cmd)


# ── searchsploit ────────────────────────────────────────────────────────────

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def searchsploit(
    *,
    search_term: str,
    exact_match: bool = False,
    additional_args: str = "",
) -> Dict[str, Any]:
    """
    Run searchsploit to search the Exploit-DB archive for known vulnerabilities and exploit code.

    :param search_term: The keyword or CVE to search for.
    :param exact_match: Perform an exact match search.
    :param additional_args: Extra searchsploit flags.
    """
    cmd = ["searchsploit"]
    if exact_match:
        cmd.append("-e")
    if search_term:
        cmd.append(search_term)
    if additional_args:
        cmd += additional_args.split()
    return _run(cmd)

# ── msfconsole ──────────────────────────────────────────────────────────────

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
async def msfconsole(
    *,
    resource_script: str = "",
    command_string: str = "",
    additional_args: str = "",
) -> Dict[str, Any]:
    """
    Run Metasploit Framework (msfconsole) in a non-interactive manner to execute modules or scripts.

    :param resource_script: Path to an msf resource script (.rc) to execute.
    :param command_string: A single msfconsole command string to execute (via -x).
    :param additional_args: Extra msfconsole flags.
    """
    cmd = ["msfconsole", "-q"]
    if resource_script:
        cmd += ["-r", resource_script]
    if command_string:
        cmd += ["-x", command_string]
    if additional_args:
        cmd += additional_args.split()
    return _run(cmd)

# ── run_shell_command ───────────────────────────────────────────────────────

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True))
async def run_shell_command(
    *,
    command: str,
    timeout: int = 300,
) -> Dict[str, Any]:
    """
    Run arbitrary shell commands directly in the Kali container environment.
    This provides low-level access to the system for running custom scripts or commands not covered by the dedicated tools.

    :param command: The bash command or script to execute.
    :param timeout: Execution timeout in seconds (default: 300).
    """
    cmd = ["bash", "-c", command]
    return _run(cmd, timeout=timeout)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="server.py",
        description="Run the Kali Linux API Server",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port for the API server (default: 8001)",
    )
    parser.add_argument(
        "--ip",
        default="0.0.0.0",
        help="IP address to bind the server to (default: 0.0.0.0)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    log.info(
        "Starting Kali FastMCP Server on %s:%d (debug=%s)",
        args.ip, args.port, args.debug,
    )
    mcp.run(transport="http", host=args.ip, port=args.port)


if __name__ == "__main__":
    main()
