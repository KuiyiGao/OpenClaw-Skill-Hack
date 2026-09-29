"""Walk filesystem for SKILL.md folders across all known agent frameworks.

Project-scope dirs (walked from cwd up to filesystem root):
    .claude/skills, .openclaw/skills, .openclaw/workspace/skills,
    .agents/skills, .cursor/skills, .codex/skills, .gemini/skills,
    .opencode/skills, .claude-plugin/skills, skills.

User-scope dirs (under $HOME):
    ~/.claude/skills, ~/.openclaw/skills, ~/.openclaw/workspace/skills,
    ~/.agents/skills, ~/.config/opencode/skills.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n(.*)$", re.DOTALL)


@dataclass
class Skill:
    """One Agent Skill loaded from disk.

    Fields the firewall actually uses are at the top. Anything extra from
    the manifest is preserved in ``raw`` so the user can inspect it.
    """
    name: str
    description: str = ""
    version: str = ""
    license: str = ""
    path: Path = field(default_factory=Path)
    scripts: list[Path] = field(default_factory=list)
    references: list[Path] = field(default_factory=list)
    assets: list[Path] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    allow_hosts: list[str] = field(default_factory=list)
    fin_capabilities: list[str] = field(default_factory=list)
    body: str = ""
    raw: dict = field(default_factory=dict)

    def to_intent(self) -> dict:
        """Reduce to the dict expected by ``build_intent_envelope``."""
        return {
            "name": self.name,
            "description": self.description,
            "allowed_tools": list(self.allowed_tools),
            "allow_hosts": list(self.allow_hosts),
            "fin_capabilities": list(self.fin_capabilities),
        }


def _parse_yaml_lite(text: str) -> dict:
    """A tolerant YAML front-matter parser for the small subset skills use.

    We deliberately do not depend on PyYAML here so the firewall's core
    has no heavy import for manifest reading; if PyYAML is installed
    elsewhere, it is used as a stronger fallback.
    """
    out: dict = {}
    cur_key: str | None = None
    cur_list: list[str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if cur_list is not None and line.startswith(" ") and line.lstrip().startswith("- "):
            cur_list.append(line.lstrip()[2:].strip().strip("\"'"))
            continue
        cur_list = None
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            if v == "" or v == "[]":
                # might be a YAML list following on indented lines
                cur_list = []
                out[k] = cur_list
                cur_key = k
                continue
            if v.startswith("[") and v.endswith("]"):
                items = [s.strip().strip("\"'") for s in v[1:-1].split(",") if s.strip()]
                out[k] = items
            else:
                out[k] = v.strip().strip("\"'")
            cur_key = k
    # Try PyYAML as a stronger fallback if available
    try:
        import yaml  # type: ignore[import-not-found]
        better = yaml.safe_load(text)
        if isinstance(better, dict):
            return better
    except Exception:
        pass
    return out


def parse_skill_md(text: str) -> tuple[dict, str]:
    """Split a SKILL.md into (frontmatter dict, markdown body)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text.strip()
    meta = _parse_yaml_lite(m.group(1))
    body = m.group(2).strip()
    return meta, body


def load_skill(path: str | Path) -> Skill | None:
    """Load one skill folder. Returns None if no SKILL.md is present."""
    p = Path(path).expanduser().resolve()
    md = p / "SKILL.md"
    if not md.exists():
        return None
    try:
        text = md.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = parse_skill_md(text)
    scripts = [c for c in (p / "scripts").glob("*") if c.is_file()] if (p / "scripts").exists() else []
    refs = [c for c in (p / "references").glob("*") if c.is_file()] if (p / "references").exists() else []
    assets = [c for c in (p / "assets").glob("*") if c.is_file()] if (p / "assets").exists() else []
    name = str(meta.get("name") or p.name)
    return Skill(
        name=name,
        description=str(meta.get("description") or ""),
        version=str(meta.get("version") or ""),
        license=str(meta.get("license") or ""),
        path=p,
        scripts=scripts,
        references=refs,
        assets=assets,
        allowed_tools=_as_list(meta.get("allowed_tools") or meta.get("allowed-tools")),
        allow_hosts=_as_list(meta.get("allow_hosts") or meta.get("allow-hosts")),
        fin_capabilities=fin_capabilities_of(meta),
        body=body,
        raw=meta,
    )


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def fin_capabilities_of(meta: dict) -> list[str]:
    """Declared financial capabilities: top-level or under ``metadata:``.

    Accepts a YAML list or a comma/space separated string.
    """
    v = meta.get("fin_capabilities") or meta.get("fin-capabilities")
    nested = meta.get("metadata")
    if v is None and isinstance(nested, dict):
        v = nested.get("fin_capabilities") or nested.get("fin-capabilities")
    if isinstance(v, str):
        v = re.split(r"[,\s]+", v)
    return [x for x in (s.strip().lower() for s in _as_list(v)) if x]


# Skill directories come from the agent registry so a new framework only has
# to be declared once (in firewall/integrations/agents.py) to become
# discoverable here. See that file's `project_skill_dirs`/`home_skill_dirs`.
from firewall.integrations.agents import home_skill_dirs, project_skill_dirs

_PROJECT_DIRS = project_skill_dirs()
_HOME_DIRS = home_skill_dirs()


def _candidate_dirs(start: Path, extra_dirs: list[Path]) -> list[Path]:
    out: list[Path] = []
    cwd = start.resolve()
    while True:
        for d in _PROJECT_DIRS:
            p = cwd / d
            if p.is_dir():
                out.append(p)
        parent = cwd.parent
        if parent == cwd:
            break
        cwd = parent
    home = Path.home()
    for d in _HOME_DIRS:
        p = home / d
        if p.is_dir():
            out.append(p)
    for e in extra_dirs:
        if e.is_dir():
            out.append(e)
    # de-dupe preserving order
    seen: set[str] = set()
    uniq: list[Path] = []
    for d in out:
        s = str(d.resolve())
        if s not in seen:
            seen.add(s)
            uniq.append(d)
    return uniq


def discover_skills(
    start: str | Path | None = None,
    extra_dirs: list[str | Path] | None = None,
) -> list[Skill]:
    """Walk all known skill directories and load every SKILL.md found."""
    s = Path(start) if start else Path.cwd()
    extras = [Path(p) for p in (extra_dirs or [])]
    skills: list[Skill] = []
    for d in _candidate_dirs(s, extras):
        for child in sorted(d.iterdir()):
            if not child.is_dir():
                continue
            sk = load_skill(child)
            if sk is not None:
                skills.append(sk)
    return skills


__all__ = ["Skill", "discover_skills", "load_skill", "parse_skill_md", "fin_capabilities_of"]
