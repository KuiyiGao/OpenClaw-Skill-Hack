"""Supervisor — turns raw log lines into normalized evidence.

The egress proxy, canary, and agent CLI each write ad-hoc text lines.
This module owns the regex set that translates those into structured
events the L2 verifier and the panel consume. Keeping the regexes here
(and not in the verifier) keeps the verifier free of stream parsing.

Line shapes the proxy and canary actually produce::

    EGRESS allow  api.deepseek.com:443
    EGRESS deny   192.0.2.10 http://192.0.2.10/ingest
    EGRESS capture POST attacker-canary.evil /collect
    CANARY-HIT    192.0.2.20  /probe
"""

from __future__ import annotations

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
