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

# Skills are baked into /app/skills at build time (COPY skills/skills/ /app/skills/).
# SKILLS_DIR env var can override for local dev (volume mount).
# supporting_files="resources" makes every file enumerable via list_resources().
skills_path = Path(os.environ.get("SKILLS_DIR", "/app/skills"))
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

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
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


@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
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

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
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

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
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

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
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

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
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

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
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

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True))
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

# ── list_skills ────────────────────────────────────────────────────────────

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def list_skills() -> list[dict[str, Any]]:
    """
    List all active skills in the Kali server's mounted skills directory, parsing metadata from SKILL.md.
    """
    import re
    import yaml
    skills = []
    try:
        if not skills_path.is_dir():
            return []

        for skill_dir in skills_path.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue

            skill_md_path = skill_dir / "SKILL.md"
            if not skill_md_path.is_file():
                continue

            name = skill_dir.name
            description = ""
            files = [f.name for f in skill_dir.iterdir() if f.is_file()]

            try:
                content = skill_md_path.read_text(encoding="utf-8")
                match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
                if match:
                    frontmatter = yaml.safe_load(match.group(1))
                    if isinstance(frontmatter, dict):
                        description = frontmatter.get("description", "")
                else:
                    lines = [line.strip() for line in content.splitlines() if line.strip()]
                    if lines:
                        description = lines[0].lstrip("#").strip()
            except Exception:
                pass

            skills.append({
                "name": name,
                "description": description,
                "files": files,
            })
    except Exception as exc:
        log.exception("Error in list_skills")
        return [{"error": str(exc)}]
    return skills

# ── read_skill ──────────────────────────────────────────────────────────────

@mcp.tool(task=True, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))
async def read_skill(
    *,
    name: str,
) -> dict[str, Any]:
    """
    Read the contents of a specific active agent skill from the Kali server's mounted skills directory.

    :param name: The identifier name of the skill (e.g. 'nightmare').
    """
    import re
    try:
        # Simple validation
        if not re.match(r"^[a-zA-Z0-9_-]+$", name):
            raise ValueError("Invalid skill name")
            
        skill_dir = skills_path / name
        if not skill_dir.is_dir():
            return {"error": f"Skill '{name}' does not exist under {skills_path}."}

        # Read SKILL.md
        skill_md_path = skill_dir / "SKILL.md"
        skill_md_content = ""
        if skill_md_path.is_file():
            skill_md_content = skill_md_path.read_text(encoding="utf-8")

        # Read supporting files recursively
        supporting_files = {}
        for root, _, files in os.walk(skill_dir):
            for file in files:
                if file == "SKILL.md" or file.startswith("."):
                    continue
                file_path = Path(root) / file
                rel_path = file_path.relative_to(skill_dir).as_posix()
                try:
                    content = file_path.read_text(encoding="utf-8")
                    supporting_files[rel_path] = content
                except UnicodeDecodeError:
                    supporting_files[rel_path] = f"[Binary File, size: {file_path.stat().st_size} bytes]"

        return {
            "name": name,
            "skill_md": skill_md_content,
            "supporting_files": supporting_files,
        }
    except Exception as exc:
        log.exception("Error in read_skill")
        return {"error": str(exc)}


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
