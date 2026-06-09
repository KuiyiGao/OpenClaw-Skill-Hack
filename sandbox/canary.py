#!/usr/bin/env python3
"""内网蜜罐 tripwire（stdlib）。任何被诱导的内部探测/外泄尝试只会打到这里，
不会有真实数据离开沙箱。命中即打印 CANARY-HIT，monitor 可见。"""
from __future__ import annotations
import json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class H(BaseHTTPRequestHandler):
    def _hit(self, m):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n).decode("utf-8", "replace")[:300] if n else ""
        sys.stdout.write("CANARY-HIT " + json.dumps(
            {"ts": time.time(), "method": m, "path": self.path, "from": self.client_address[0],
             "body": body}, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok":true}')

    def do_GET(self):  self._hit("GET")
    def do_POST(self): self._hit("POST")
    def log_message(self, *a): pass


if __name__ == "__main__":
    print("CANARY-HIT " + json.dumps({"event": "canary_start", "port": 8088}))
    sys.stdout.flush()
    ThreadingHTTPServer(("0.0.0.0", 8088), H).serve_forever()
