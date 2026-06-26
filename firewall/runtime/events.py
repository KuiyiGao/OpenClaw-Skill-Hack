"""Event emitter — appends one JSON object per line to ``events.jsonl``.

This is what ``firewall start`` writes and ``firewall panel`` tails.
Format::

    {"ts": "<ISO-8601>", "kind": "<verdict|egress|canary|usage|info>",
     "skill": "<name|null>", ...}

Schema is open-ended on purpose: new event kinds can be added without
breaking existing readers. The panel ignores unknown keys.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


_LOCK = Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EventEmitter:
    """Thread-safe JSONL appender with size-based rotation."""

    def __init__(self, path: str | Path, *, max_mb: int = 100):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_mb * 1024 * 1024

    def emit(self, kind: str, **fields) -> None:
        payload = {"ts": _now(), "kind": kind, **fields}
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with _LOCK:
            if self.path.exists() and self.path.stat().st_size > self.max_bytes:
                rotated = self.path.with_suffix(self.path.suffix + ".1")
                if rotated.exists():
                    rotated.unlink()
                os.replace(self.path, rotated)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)

    @contextmanager
    def span(self, kind: str, **fields):
        t0 = time.monotonic()
        yield
        self.emit(kind, dur_ms=int((time.monotonic() - t0) * 1000), **fields)


def tail_events(path: str | Path, *, n: int = 200) -> list[dict]:
    """Read the last ``n`` events from disk (used by ``firewall panel`` cold-start)."""
    p = Path(path).expanduser()
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f.readlines()[-n:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


__all__ = ["EventEmitter", "tail_events"]
