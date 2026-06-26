"""Zero-trust HTTP egress proxy.

Listens on ``127.0.0.1:8080`` by default and acts as an HTTP/HTTPS
forward proxy:

* requests whose host matches ``cfg.egress.allow_hosts`` are passed
  through to the upstream;
* requests whose host matches ``cfg.egress.deny_hosts`` (or is in the
  hostile/pseudo-TLD lists) are **denied** — the body is recorded for
  evidence and the client receives 403;
* anything else is **captured** — the body is recorded as evidence but
  the upstream call is short-circuited (the request never leaves);
* every decision is emitted as an event line the supervisor consumes.

This is the "L1 containment" layer. Detection lives in
``firewall.runtime.firewall`` and is kept strictly separate (the L2
verifier in detector mode subtracts honeypot captures from the verdict).
"""

from __future__ import annotations

import http.client
import http.server
import json
import socketserver
import sys
import threading
import urllib.parse
from contextlib import closing
from pathlib import Path
from typing import Any

from firewall.config import Config, config_path, load_config
from firewall.runtime.events import EventEmitter


class _LiveConfig:
    """Re-read config from disk if the TOML mtime changed since last read.

    Cheap enough to call once per request (stat + maybe parse). Means that
    \`firewall config mode strict\` from another shell takes effect on the
    next request without restarting the proxy.
    """
    __slots__ = ("_cfg", "_path", "_mtime")

    def __init__(self, initial: Config) -> None:
        self._cfg = initial
        self._path = config_path()
        try:
            self._mtime = self._path.stat().st_mtime
        except OSError:
            self._mtime = 0.0

    def get(self) -> Config:
        try:
            mt = self._path.stat().st_mtime
        except OSError:
            return self._cfg
        if mt != self._mtime:
            try:
                self._cfg = load_config(self._path)
                self._mtime = mt
            except Exception:
                pass
        return self._cfg


class _Handler(http.server.BaseHTTPRequestHandler):
    live_cfg: _LiveConfig
    emitter: EventEmitter

    @property
    def cfg(self) -> Config:
        return self.live_cfg.get()

    # We log to events.jsonl, not stderr.
    def log_message(self, fmt, *args) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        return

    def _emit(self, kind: str, host: str, method: str, path: str, **extra) -> None:
        self.emitter.emit(kind, host=host, method=method, path=path, **extra)

    # --- HTTPS (CONNECT) ------------------------------------------------
    def do_CONNECT(self) -> None:  # noqa: N802
        host, _, port = self.path.partition(":")
        mode = self.cfg.policy.mode
        if self.cfg.host_denied(host) or self.cfg.is_hostile_host(host):
            if mode == "observe":
                self._emit("egress.allow", host, "CONNECT", self.path,
                           reason="observe-mode would-deny")
                # fall through to upstream tunnel
            else:
                self._emit("egress.deny", host, "CONNECT", self.path)
                self.send_error(403, "denied by firewall")
                return
        elif not self.cfg.host_allowed(host):
            # Unknown host: with CONNECT we can't inspect the body, so the
            # mode picks between block (strict/balanced) and let-through
            # (observe). The capture event records the attempt either way.
            self._emit("egress.capture", host, "CONNECT", self.path)
            if mode != "observe":
                self.send_error(403, "denied by firewall (not in allow_hosts)")
                return
        try:
            upstream = http.client.HTTPSConnection(host, int(port or "443"), timeout=10)
            upstream.connect()
        except OSError as e:
            self.send_error(502, f"upstream: {e}")
            return
        self.send_response(200, "Connection Established")
        self.end_headers()
        self._emit("egress.allow", host, "CONNECT", self.path)
        self._splice(self.connection, upstream.sock)

    @staticmethod
    def _splice(a, b) -> None:
        import select
        socks = [a, b]
        try:
            while True:
                r, _, _ = select.select(socks, [], [], 30)
                if not r:
                    break
                for s in r:
                    data = s.recv(8192)
                    if not data:
                        return
                    other = b if s is a else a
                    other.sendall(data)
        finally:
            try: a.close()
            except OSError: pass
            try: b.close()
            except OSError: pass

    # --- HTTP -----------------------------------------------------------
    def _proxy_http(self) -> None:
        u = urllib.parse.urlsplit(self.path)
        host = u.hostname or self.headers.get("Host", "").split(":")[0]
        method = self.command
        path = u.path or "/"
        if u.query:
            path += "?" + u.query
        body = b""
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            body = self.rfile.read(length)
        mode = self.cfg.policy.mode  # strict | balanced | observe
        if self.cfg.host_denied(host) or self.cfg.is_hostile_host(host):
            if mode == "observe":
                self._emit("egress.allow", host, method, path,
                           reason="observe-mode would-deny")
                # fall through to upstream forward below
            else:
                self._emit("egress.deny", host, method, path, body_len=len(body))
                self.send_error(403, "denied by firewall")
                return
        elif not self.cfg.host_allowed(host):
            # Unknown host. Mode decides:
            #   strict   -> 403 deny (treat unknown as hostile)
            #   balanced -> short-circuit with 204 + capture body as evidence
            #   observe  -> capture event then forward upstream
            if mode == "strict":
                self._emit("egress.deny", host, method, path,
                           reason="strict-mode unknown host")
                self.send_error(403, "unknown host (strict mode)")
                return
            if mode == "balanced":
                self._emit("egress.capture", host, method, path,
                           body_preview=body[:120].decode("utf-8", "replace"))
                # NOTE: use 200 + tiny body rather than bare 204. Docker
                # Desktop's gvproxy on macOS drops 204 responses without an
                # explicit Content-Length on the loopback port-forward,
                # which surfaces as "Empty reply from server" on the host.
                payload = b'{"firewall":"captured"}\n'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            # observe: record and let through
            self._emit("egress.capture", host, method, path,
                       body_preview=body[:120].decode("utf-8", "replace"),
                       reason="observe-mode would-capture")
        # Allowed: forward.
        try:
            with closing(http.client.HTTPConnection(host, u.port or 80, timeout=10)) as upstream:
                upstream.request(method, path, body=body, headers=dict(self.headers))
                resp = upstream.getresponse()
                self.send_response(resp.status, resp.reason)
                for k, v in resp.getheaders():
                    if k.lower() in {"transfer-encoding", "connection"}:
                        continue
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
                self._emit("egress.allow", host, method, path, status=resp.status)
        except OSError as e:
            self.send_error(502, f"upstream: {e}")

    do_GET = _proxy_http       # type: ignore[assignment]
    do_POST = _proxy_http      # type: ignore[assignment]
    do_PUT = _proxy_http       # type: ignore[assignment]
    do_PATCH = _proxy_http     # type: ignore[assignment]
    do_DELETE = _proxy_http    # type: ignore[assignment]


class _ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(host: str = "127.0.0.1", port: int = 8080, cfg: Config | None = None) -> None:
    if cfg is None:
        cfg = load_config()
    emitter = EventEmitter(cfg.state.events_path)
    handler = _Handler
    handler.live_cfg = _LiveConfig(cfg)
    handler.emitter = emitter
    with _ThreadedServer((host, port), handler) as srv:
        emitter.emit("info", message="egress-proxy listening",
                     host=host, port=port, policy=cfg.policy.mode)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            srv.shutdown()


if __name__ == "__main__":
    serve()
