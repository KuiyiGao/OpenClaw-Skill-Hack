from __future__ import annotations

import json
import os
import select
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOW = [d.strip().lstrip(".").lower() for d in os.environ.get("EGRESS_ALLOW", "").split(",") if d.strip()]
HTTP_MODE = os.environ.get("EGRESS_HTTP", "capture").lower()


def _log(msg: str) -> None:
    sys.stdout.write("EGRESS " + msg + "\n")
    sys.stdout.flush()


def allowed(host: str) -> bool:
    host = host.split(":")[0].lower()
    return any(host == d or host.endswith("." + d) for d in ALLOW)


class Proxy(BaseHTTPRequestHandler):
    def do_CONNECT(self):
        host = self.path.split(":")[0]
        port = int(self.path.split(":")[1]) if ":" in self.path else 443
        if not allowed(host):
            _log(f"DENY CONNECT {self.path}")
            self.send_error(403, "egress blocked by allowlist")
            return
        try:
            upstream = socket.create_connection((host, port), timeout=10)
        except OSError as e:
            _log(f"FAIL CONNECT {self.path} {e}")
            self.send_error(502, "upstream unreachable")
            return
        _log(f"ALLOW CONNECT {self.path}")
        self.connection.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        self._tunnel(self.connection, upstream)

    @staticmethod
    def _tunnel(a: socket.socket, b: socket.socket) -> None:
        try:
            while True:
                r, _, _ = select.select([a, b], [], [], 60)
                if not r:
                    break
                for s in r:
                    data = s.recv(8192)
                    if not data:
                        return
                    (b if s is a else a).sendall(data)
        except OSError:
            pass
        finally:
            for s in (a, b):
                try:
                    s.close()
                except OSError:
                    pass

    def _exfil(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        host = self.headers.get("Host", "?")
        if HTTP_MODE == "capture":
            _log("CAPTURE " + json.dumps(
                {"method": self.command, "host": host, "path": self.path, "bytes": n, "body": body[:1000]},
                ensure_ascii=False))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            _log(f"DENY {self.command} {host}{self.path}")
            self.send_error(403, "plain HTTP egress blocked")

    do_GET = do_POST = do_PUT = do_DELETE = _exfil

    def log_message(self, *a):
        return


if __name__ == "__main__":
    _log(f"start allow={ALLOW} http={HTTP_MODE}")
    ThreadingHTTPServer(("0.0.0.0", 3128), Proxy).serve_forever()
