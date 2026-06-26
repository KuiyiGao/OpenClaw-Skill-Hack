"""Backend for the browser panel.

Serves `web.html` at `/` and streams the live events file at
`/events.jsonl`, so the single-file dashboard has something to poll
without the user running a separate `python -m http.server` and without
exposing the whole state directory. Localhost-only.
"""
from __future__ import annotations

import http.server
import webbrowser
from functools import partial
from pathlib import Path

_HTML = Path(__file__).with_name("web.html")


class _Handler(http.server.BaseHTTPRequestHandler):
    events_path: str

    def log_message(self, *_a) -> None:  # silence default stderr logging
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] in ("/", "/index.html"):
            self._send(_HTML.read_bytes(), "text/html; charset=utf-8")
        elif self.path.split("?")[0] == "/events.jsonl":
            p = Path(self.events_path).expanduser()
            data = p.read_bytes() if p.exists() else b""
            self._send(data, "application/x-ndjson")
        else:
            self.send_error(404)

    def _send(self, body: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve_web(events_path: str, port: int = 8090, open_browser: bool = True) -> None:
    handler = partial(_Handler)
    handler.events_path = events_path  # type: ignore[attr-defined]
    _Handler.events_path = events_path
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"browser panel: {url}   (events <- {events_path})")
    print("Ctrl-C to stop.")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
