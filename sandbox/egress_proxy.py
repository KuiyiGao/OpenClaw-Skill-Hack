from __future__ import annotations

import ipaddress
import json
import os
import select
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOW = [d.strip().lstrip(".").lower() for d in os.environ.get("EGRESS_ALLOW", "").split(",") if d.strip()]
HTTP_MODE = os.environ.get("EGRESS_HTTP", "capture").lower()

try:
    from egress_policy import decide as _policy
except Exception:
    _policy = None


def _log(msg: str) -> None:
    # Emit one "EGRESS ..." line to stdout for the supervisor (outer layer) to classify.
    sys.stdout.write("EGRESS " + msg + "\n")
    sys.stdout.flush()


def allowed(host: str) -> bool:
    # True if host exactly matches or is a subdomain of an EGRESS_ALLOW entry.
    host = host.split(":")[0].lower()
    return any(host == d or host.endswith("." + d) for d in ALLOW)


def blocked_dest(host: str) -> bool:
    # True for non-public IP literals: cloud metadata, link-local, private, loopback, CGNAT.
    h = host.split(":")[0].strip("[]")
    try:
        return not ipaddress.ip_address(h).is_global
    except ValueError:
        return False


def policy(phase: str, host: str, method, body):
    # Consult the optional egress_policy.decide() firewall hook; may only return "deny"/"capture" or None.
    if _policy is None:
        return None
    try:
        d = _policy(phase, host, method, body)
        return d if d in ("deny", "capture") else None
    except Exception:
        return None


class Proxy(BaseHTTPRequestHandler):
    def do_CONNECT(self):
        # HTTPS path: hard-deny non-public, enforce allowlist + firewall hook, then relay encrypted bytes.
        host = self.path.split(":")[0]
        port = int(self.path.split(":")[1]) if ":" in self.path else 443
        if blocked_dest(host):
            _log(f"DENY CONNECT {self.path} (non-public)")
            self.send_error(403, "egress blocked")
            return
        if not allowed(host) or policy("connect", host, "CONNECT", None) == "deny":
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
        # Bidirectionally relay raw bytes between client and upstream until either side closes.
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
        # Plain-HTTP path: hard-deny non-public, then honeypot-capture or deny per the hook / EGRESS_HTTP.
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        host = self.headers.get("Host", "?")
        if blocked_dest(host):
            _log(f"DENY {self.command} {host}{self.path} (non-public)")
            self.send_error(403, "egress blocked")
            return
        decision = policy("http", host, self.command, body) or HTTP_MODE
        if decision == "capture":
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
        # Silence the default per-request access log; only EGRESS lines are emitted.
        return


if __name__ == "__main__":
    _log(f"start allow={ALLOW} http={HTTP_MODE} policy={'on' if _policy else 'off'}")
    ThreadingHTTPServer(("0.0.0.0", 3128), Proxy).serve_forever()
