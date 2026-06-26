"""Internal honeypot tripwire — a tiny HTTP server that records hits.

Bound to ``127.0.0.1:8088`` by default. Any inbound request is logged
as ``CANARY-HIT`` so the supervisor records it as a containment signal.
The L2 verifier in detector mode subtracts this from the verdict (it is
containment, not evidence — invariant 3).
"""

from __future__ import annotations

import http.server
from firewall.config import Config, load_config
from firewall.runtime.events import EventEmitter


class _Handler(http.server.BaseHTTPRequestHandler):
    emitter: EventEmitter

    def log_message(self, fmt, *args) -> None:  # noqa: N802
        return

    def _hit(self) -> None:
        self.emitter.emit("canary", host=self.client_address[0],
                          path=self.path, method=self.command)
        self.send_response(204)
        self.end_headers()

    do_GET = _hit       # type: ignore[assignment]
    do_POST = _hit      # type: ignore[assignment]
    do_PUT = _hit       # type: ignore[assignment]


def serve(host: str = "127.0.0.1", port: int = 8088, cfg: Config | None = None) -> None:
    if cfg is None:
        cfg = load_config()
    _Handler.emitter = EventEmitter(cfg.state.events_path)
    with http.server.ThreadingHTTPServer((host, port), _Handler) as srv:
        _Handler.emitter.emit("info", message="canary listening", host=host, port=port)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            srv.shutdown()


if __name__ == "__main__":
    serve()
