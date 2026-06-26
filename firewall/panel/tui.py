"""Live firewall panel.

Layout (Textual, gracefully reflows to 80×24)::

    +-- Header -----------------------------------------------------------+
    | firewall panel   driver: deepseek-chat   policy: balanced   time   |
    +-- Passed/Blocked (A) -------+-- Session (B) ----------------------+
    | time   skill verdict reason | skills seen   …                    |
    | 23:13  …    PASS    -       | allowed       …                    |
    | 23:13  …    BLOCK   …       | deferred      …                    |
    | …                           | blocked       …                    |
    |                             +-- API usage (C) --------------------+
    |                             | calls   …  tokens in  …  cost $…   |
    |                             +-- Recent events (D) ---------------+
    |                             | tailing events.jsonl …             |
    +-----------------------------+------------------------------------+
    | Footer: q quit · p pause · c clear · f filter                    |
    +------------------------------------------------------------------+

Tails ``state.events_path`` (default ``~/.local/state/firewall/events.jsonl``).
Read-only; ``firewall start`` is what writes the events.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, Log, Static


def _now_local() -> str:
    return datetime.now().strftime("%H:%M:%S")


class SessionPanel(Static):
    seen: reactive[int] = reactive(0)
    allowed: reactive[int] = reactive(0)
    deferred: reactive[int] = reactive(0)
    blocked: reactive[int] = reactive(0)
    started: float = 0.0

    def on_mount(self) -> None:
        self.started = time.monotonic()
        self.set_interval(1.0, self.refresh)

    def render(self) -> str:
        block_rate = (self.blocked / self.seen * 100) if self.seen else 0.0
        up = int(time.monotonic() - self.started)
        h, rem = divmod(up, 3600)
        m, s = divmod(rem, 60)
        return (
            "[b]Session[/b]\n"
            f"skills seen    {self.seen}\n"
            f"allowed        [green]{self.allowed}[/green]\n"
            f"deferred       [yellow]{self.deferred}[/yellow]\n"
            f"blocked        [red]{self.blocked}[/red]\n"
            f"block rate     {block_rate:5.1f}%\n"
            f"uptime         {h:02d}:{m:02d}:{s:02d}"
        )


class UsagePanel(Static):
    calls: reactive[int] = reactive(0)
    tok_in: reactive[int] = reactive(0)
    tok_out: reactive[int] = reactive(0)
    cost: reactive[float] = reactive(0.0)
    model: str = "—"

    def render(self) -> str:
        cost_s = f"${self.cost:.4f}" if self.cost else "$ —"
        return (
            "[b]API usage[/b]\n"
            f"driver       {self.model}\n"
            f"calls        {self.calls}\n"
            f"tokens in    {self.tok_in:,}\n"
            f"tokens out   {self.tok_out:,}\n"
            f"est. cost    {cost_s}"
        )


VERDICT_STYLE = {
    "benign":     ("PASS",   "green"),
    "suspicious": ("DEFER",  "yellow"),
    "malicious":  ("BLOCK",  "red"),
}


class FirewallPanel(App):
    CSS = """
    Screen { layout: grid; grid-size: 2 3; grid-columns: 3fr 2fr; grid-rows: 3fr 1fr 2fr; }
    #table-cell  { row-span: 3; }
    #session-cell { height: auto; }
    #usage-cell   { height: auto; }
    #log-cell     { height: 1fr; }
    DataTable     { width: 100%; }
    SessionPanel, UsagePanel { padding: 1 2; border: round $primary; }
    """

    BINDINGS = [
        Binding("q", "quit", "quit"),
        Binding("p", "toggle_pause", "pause"),
        Binding("c", "clear_table", "clear"),
    ]

    def __init__(self, events_path: str | Path, cfg: Any | None = None) -> None:
        super().__init__()
        self.events_path = Path(events_path).expanduser()
        self.cfg = cfg
        self.paused: bool = False
        self._file_pos: int = 0
        self._prices = getattr(cfg, "prices", {}) if cfg else {}
        self._driver_key = (
            f"{cfg.driver.provider}/{cfg.driver.model}" if cfg else ""
        )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="table-cell"):
            table = DataTable(zebra_stripes=True, cursor_type="row")
            table.add_columns("time", "skill", "verdict", "reason")
            yield table
        with Container(id="session-cell"):
            yield SessionPanel(id="session")
        with Container(id="usage-cell"):
            yield UsagePanel(id="usage")
        with Container(id="log-cell"):
            yield Log(id="recent", highlight=True, auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "firewall panel"
        if self.cfg is not None:
            self.sub_title = f"driver: {self.cfg.driver.model}   policy: {self.cfg.policy.mode}"
            usage = self.query_one("#usage", UsagePanel)
            usage.model = self.cfg.driver.model
        # tail new events only
        if self.events_path.exists():
            self._file_pos = self.events_path.stat().st_size
        self.set_interval(0.5, self._poll)

    def action_toggle_pause(self) -> None:
        self.paused = not self.paused

    def action_clear_table(self) -> None:
        self.query_one(DataTable).clear()

    def _poll(self) -> None:
        if self.paused or not self.events_path.exists():
            return
        try:
            with self.events_path.open("r", encoding="utf-8") as f:
                f.seek(self._file_pos)
                new_lines = f.readlines()
                self._file_pos = f.tell()
        except OSError:
            return
        for raw in new_lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            self._ingest(ev)

    def _ingest(self, ev: dict) -> None:
        kind = ev.get("kind")
        if kind == "verdict":
            self._on_verdict(ev)
        elif kind == "usage":
            self._on_usage(ev)
        elif kind in {"egress", "canary", "info"}:
            self._on_log(ev)

    def _on_verdict(self, ev: dict) -> None:
        verdict = (ev.get("verdict") or "benign").lower()
        label, color = VERDICT_STYLE.get(verdict, ("?", "white"))
        reason = ev.get("reason") or (", ".join(ev.get("confirmations") or [])[:60]) or "-"
        skill = ev.get("skill") or "—"
        t = _short_ts(ev.get("ts"))
        tbl = self.query_one(DataTable)
        tbl.add_row(t, skill, f"[{color}]{label}[/{color}]", reason)
        keep = (self.cfg.panel.keep_rows if self.cfg else 200)
        if tbl.row_count > keep:
            tbl.remove_row(tbl.ordered_rows[0].key)
        sp = self.query_one("#session", SessionPanel)
        sp.seen += 1
        if verdict == "benign":
            sp.allowed += 1
        elif verdict == "malicious":
            sp.blocked += 1
        else:
            sp.deferred += 1

    def _on_usage(self, ev: dict) -> None:
        usage = self.query_one("#usage", UsagePanel)
        usage.calls += int(ev.get("calls") or 1)
        ti = int(ev.get("tokens_in") or 0)
        to = int(ev.get("tokens_out") or 0)
        usage.tok_in += ti
        usage.tok_out += to
        price = self._prices.get(self._driver_key) or {}
        if price:
            usage.cost += (ti / 1_000_000) * float(price.get("input", 0))
            usage.cost += (to / 1_000_000) * float(price.get("output", 0))

    def _on_log(self, ev: dict) -> None:
        log = self.query_one("#recent", Log)
        host = ev.get("host") or ""
        path = ev.get("path") or ""
        t = _short_ts(ev.get("ts"))
        log.write_line(f"{t}  {ev.get('kind'):<7}  {host}  {path}")


def _short_ts(iso: str | None) -> str:
    if not iso:
        return _now_local()
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M:%S")
    except Exception:
        return _now_local()


def run_panel(events_path: str | Path, cfg=None) -> None:
    FirewallPanel(events_path=events_path, cfg=cfg).run()


__all__ = ["FirewallPanel", "run_panel"]
