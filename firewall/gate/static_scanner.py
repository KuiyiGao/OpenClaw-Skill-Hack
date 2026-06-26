"""Built-in L0 static scanner.

This is intentionally small and pattern-driven so users can audit and
extend it. The classifier never decides install/no-install on its own —
it emits :class:`Finding` records with a severity, and the supervisor
applies the prescan rule (only CRITICAL hard-blocks; HIGH/MEDIUM defer
to the L2 runtime layer; see ``firewall.runtime.firewall`` invariant 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from firewall.config import Config


SEVERITIES = ("NONE", "INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")


@dataclass
class Finding:
    severity: str         # one of SEVERITIES
    rule: str
    file: str
    evidence: str


# Patterns kept tiny on purpose. Users extend these in their own scanner
# subclass or via ``judge.compliance_patterns`` / ``judge.refusal_patterns``
# in config.toml. The whole point is non-empirical: a short, named list of
# well-defined rules — not an open-ended judge prompt.
_HIDDEN_HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
_SUS_FRONTMATTER_KEYS = ("bypass", "ignore_security", "disable_firewall")
_SHELL_FETCH_RE = re.compile(r"\b(curl|wget|fetch|nc|netcat)\b\s+[\w./:-]*\b", re.I)


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def scan_skill_dir(d: Path, cfg: Config) -> list[Finding]:
    """Scan one skill folder. Returns Findings sorted by severity desc."""
    d = Path(d)
    findings: list[Finding] = []

    md = d / "SKILL.md"
    if md.exists():
        text = _read(md)
        findings.extend(_scan_md(md, text))

    for child in d.rglob("*"):
        if not child.is_file():
            continue
        if child.suffix in {".py", ".sh", ".js", ".ts"}:
            findings.extend(_scan_code(child, _read(child), cfg))

    # also: any sink/source patterns from the config the user added
    for child in d.rglob("*"):
        if child.is_file() and child.suffix in {".py", ".sh", ".js", ".ts"}:
            text = _read(child)
            if cfg.is_secret_source(text) and cfg.is_network_sink(text):
                findings.append(Finding(
                    "HIGH",
                    "config:secret_source+network_sink",
                    str(child),
                    "config-defined patterns matched in same file",
                ))

    # de-dupe by (rule, file, evidence)
    seen: set[tuple[str, str, str]] = set()
    uniq: list[Finding] = []
    for f in findings:
        k = (f.rule, f.file, f.evidence[:80])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(f)

    uniq.sort(key=lambda f: SEVERITIES.index(f.severity), reverse=True)
    return uniq


def _scan_md(md: Path, text: str) -> list[Finding]:
    out: list[Finding] = []
    # Hidden HTML comments are a common prompt-injection vehicle.
    for m in _HIDDEN_HTML_COMMENT_RE.finditer(text):
        body = m.group(1).strip()
        if len(body) < 8:
            continue
        # Only flag if the comment contains instruction-shaped content
        if re.search(r"\b(ignore|bypass|disregard|override)\b", body, re.I):
            out.append(Finding("HIGH", "hidden_instruction_in_comment",
                               str(md), body[:80]))
    low = text.lower()
    for key in _SUS_FRONTMATTER_KEYS:
        if key in low:
            out.append(Finding("MEDIUM", f"frontmatter:{key}", str(md), key))
    return out


def _scan_code(path: Path, text: str, cfg: Config) -> list[Finding]:
    out: list[Finding] = []
    # Shell fetch commands with embedded URLs are a strong hint.
    for m in _SHELL_FETCH_RE.finditer(text):
        out.append(Finding("MEDIUM", "shell_fetch",
                           str(path), m.group(0)[:80]))
    # Look for hostile hosts directly named in the source.
    for host_sub in cfg.taint.exfil_host_substrings:
        if host_sub.lower() in text.lower():
            out.append(Finding("CRITICAL", "hostile_host_literal",
                               str(path), host_sub))
    return out


__all__ = ["Finding", "scan_skill_dir", "SEVERITIES"]
