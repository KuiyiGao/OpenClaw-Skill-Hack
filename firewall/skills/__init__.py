"""Framework-agnostic Agent Skill discovery + manifest parsing.

A skill is a filesystem directory whose name matches a ``name`` field
in a Markdown manifest. Every framework (Anthropic SDK, Claude Code,
OpenClaw, OpenCode, Cursor) resolves skills by walking known directories;
we hook at the filesystem layer so the firewall does not need to know
which agent is loading them. See ``discover.py``.
"""

from firewall.skills.discover import (
    Skill,
    discover_skills,
    load_skill,
    parse_skill_md,
)

__all__ = ["Skill", "discover_skills", "load_skill", "parse_skill_md"]
