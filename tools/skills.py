"""
tools/skills.py
===============
FastMCP Tools for managing agent skills dynamically in a shared skills folder.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from app import general
from mcp.types import ToolAnnotations

log = logging.getLogger(__name__)

SKILLS_ROOT = Path("/app/skills")

def _validate_skill_name(name: str) -> None:
    """Validate skill name to prevent directory traversal attacks."""
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        raise ValueError(
            f"Invalid skill name '{name}'. Only alphanumeric characters, dashes, and underscores are allowed."
        )

def _validate_file_name(name: str) -> None:
    """Validate supporting file name to prevent directory traversal attacks."""
    if not re.match(r"^[a-zA-Z0-9_.-]+$", name):
        raise ValueError(
            f"Invalid file name '{name}'. Only alphanumeric characters, dots, dashes, and underscores are allowed."
        )


@general.tool(
    description="Create or update an agent skill in the shared skills directory.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
)
async def create_or_update_skill(
    *,
    name: str,
    skill_md_content: str,
    supporting_files: Optional[Dict[str, str]] = None,
) -> str:
    """
    Create or update an agent skill directory with a SKILL.md file and supporting files.

    :param name: The identifier name of the skill (e.g. 'pdf-processing').
    :param skill_md_content: Markdown content of the main SKILL.md file.
    :param supporting_files: Optional dict mapping filenames to their contents (e.g. {'reference.md': 'content...'}).
    """
    try:
        _validate_skill_name(name)
        skill_dir = SKILLS_ROOT / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write SKILL.md
        skill_md_path = skill_dir / "SKILL.md"
        skill_md_path.write_text(skill_md_content, encoding="utf-8")

        # Write supporting files
        if supporting_files:
            for filename, content in supporting_files.items():
                _validate_file_name(filename)
                file_path = skill_dir / filename
                file_path.write_text(content, encoding="utf-8")

        return f"Successfully created/updated skill '{name}' under {skill_dir}"
    except Exception as exc:
        log.exception("Error in create_or_update_skill")
        return f"Error: {exc}"


@general.tool(
    description="Delete an agent skill from the shared skills directory.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)
)
async def delete_skill(
    *,
    name: str,
) -> str:
    """
    Delete an agent skill directory recursively.

    :param name: The identifier name of the skill to delete (e.g. 'pdf-processing').
    """
    try:
        _validate_skill_name(name)
        skill_dir = SKILLS_ROOT / name

        if not skill_dir.is_dir():
            return f"Skill '{name}' does not exist under {SKILLS_ROOT}."

        shutil.rmtree(skill_dir)
        return f"Successfully deleted skill '{name}'"
    except Exception as exc:
        log.exception("Error in delete_skill")
        return f"Error: {exc}"


@general.tool(
    description="List all active agent skills in the shared skills directory.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
)
async def list_skills() -> List[Dict[str, Any]]:
    """
    List all active skills, parsing metadata from their SKILL.md frontmatter if available.
    """
    skills = []
    try:
        if not SKILLS_ROOT.is_dir():
            return []

        for skill_dir in SKILLS_ROOT.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_md_path = skill_dir / "SKILL.md"
            if not skill_md_path.is_file():
                continue

            name = skill_dir.name
            description = ""
            files = [f.name for f in skill_dir.iterdir() if f.is_file()]

            # Try to parse frontmatter for description
            try:
                content = skill_md_path.read_text(encoding="utf-8")
                # Detect YAML frontmatter
                match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
                if match:
                    frontmatter = yaml.safe_load(match.group(1))
                    if isinstance(frontmatter, dict):
                        description = frontmatter.get("description", "")
                else:
                    # Fall back to first line
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
        # Return error info in standard format
        return [{"error": str(exc)}]

    return skills
