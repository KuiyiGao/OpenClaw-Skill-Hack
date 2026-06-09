#!/usr/bin/env python3
"""Tiny egress allowlist proxy (the core safety layer).

Only domains in EGRESS_ALLOW are reachable (HTTPS via CONNECT). Everything else --
arbitrary exfil targets, cloud metadata (169.254.x / 100.100.100.200), plain HTTP --
is denied. Denied attempts print "EGRESS DENY" so the monitor can see them.
"""
from __future__ import annotations

import os
import select
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOW = [d.strip().lstrip(".").lower() for d in os.environ.get("EGRESS_ALLOW", "").split(",") if d.strip()]


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

    def _deny_http(self):
        _log(f"DENY {self.command} {self.path}")
        self.send_error(403, "plain HTTP egress blocked")

    do_GET = do_POST = do_PUT = do_DELETE = _deny_http

    def log_message(self, *a):
        return


if __name__ == "__main__":
    _log(f"start allow={ALLOW}")
    ThreadingHTTPServer(("0.0.0.0", 3128), Proxy).serve_forever()
