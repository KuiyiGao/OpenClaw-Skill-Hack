"""Supervisor — turns raw log lines into normalized evidence.

The egress proxy, canary, and older agent logs each write their own line
shapes. This module translates those into structured events the L2
verifier and the panel consume. Keeping the regexes here
(and not in the verifier) keeps the verifier free of stream parsing.

Two line shapes are accepted. What the proxy and canary write to
``events.jsonl`` (one JSON object per line, see ``events.py``)::

    {"ts": "...", "kind": "egress.capture", "host": "attacker-canary.evil",
     "method": "POST", "path": "/collect"}
    {"ts": "...", "kind": "canary", "host": "192.0.2.20", "path": "/probe"}

and the legacy plain-text log format::

    EGRESS allow  api.deepseek.com:443
    EGRESS deny   192.0.2.10 http://192.0.2.10/ingest
    EGRESS capture POST attacker-canary.evil /collect
    CANARY-HIT    192.0.2.20  /probe
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


_EGRESS_RE = re.compile(
    r"^EGRESS\s+(?P<kind>allow|deny|capture)\s+"
    r"(?:(?P<method>[A-Z]+)\s+)?"
    r"(?P<host>[A-Za-z0-9.\-]+)"
    r"(?:[:/]\S*)?\s*"
    r"(?P<rest>.*)$"
)
_CANARY_RE = re.compile(
    r"^CANARY-HIT\s+(?P<src>\S+)\s+(?P<path>\S+)"
)


@dataclass
class Event:
    kind: str            # egress | canary | tool | answer
    host: str = ""
    method: str = ""
    path: str = ""
    detail: str = ""
    raw: str = ""


def parse_line(line: str) -> Event | None:
    line = line.rstrip("\n").strip()
    if not line:
        return None
    if line.startswith("{"):
        return _parse_json_event(line)
    m = _EGRESS_RE.match(line)
    if m:
        return Event(
            kind=f"egress.{m.group('kind')}",
            host=m.group("host") or "",
            method=m.group("method") or "",
            path=(m.group("rest") or "").strip(),
            raw=line,
        )
    m = _CANARY_RE.match(line)
    if m:
        return Event(kind="canary", host=m.group("src"), path=m.group("path"), raw=line)
    return None


def _parse_json_event(line: str) -> Event | None:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    kind = str(obj.get("kind") or "")
    if not (kind.startswith("egress.") or kind == "canary"):
        return None
    return Event(
        kind=kind,
        host=str(obj.get("host") or ""),
        method=str(obj.get("method") or ""),
        path=str(obj.get("path") or ""),
        detail=str(obj.get("reason") or ""),
        raw=line,
    )


def evidence_from_events(events: list[Event], *, answer: str = "") -> dict:
    """Group parsed events into the dict shape ``analyze_iar`` expects."""
    egress = []
    canary_hit = False
    captured = False
    for e in events:
        if e.kind.startswith("egress."):
            egress.append({"host": e.host, "method": e.method, "path": e.path})
            if e.kind == "egress.capture":
                captured = True
        elif e.kind == "canary":
            canary_hit = True
    return {
        "egress": egress,
        "answer": answer,
        "exfil_captured": captured,
        "canary_hit": canary_hit,
        "tool_calls": [],
    }


__all__ = ["Event", "parse_line", "evidence_from_events"]
