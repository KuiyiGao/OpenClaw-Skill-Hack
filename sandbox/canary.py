from __future__ import annotations
import json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class H(BaseHTTPRequestHandler):
    def _hit(self, method):
        # Record any inbound request as a CANARY-HIT (an internal probe); serve only a dummy 200.
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n).decode("utf-8", "replace")[:300] if n else ""
        sys.stdout.write("CANARY-HIT " + json.dumps(
            {"ts": time.time(), "method": method, "path": self.path,
             "from": self.client_address[0], "body": body}, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_GET(self):  self._hit("GET")
    def do_POST(self): self._hit("POST")
    def log_message(self, *a): pass


if __name__ == "__main__":
    # Internal honeypot tripwire: a lure service on the internal network; any hit means a probe.
    print("CANARY-HIT " + json.dumps({"event": "canary_start", "port": 8088}))
    sys.stdout.flush()
    ThreadingHTTPServer(("0.0.0.0", 8088), H).serve_forever()
