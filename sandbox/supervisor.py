from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from datetime import datetime

EVENTS = os.environ.get("LAB_EVENTS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_events", "events.jsonl"))
COLOR = {"OK": "#3aa76d", "INFO": "#888", "FLAG": "#c9a227", "BLOCKED": "#c4632a", "CRITICAL": "#d33"}
PREFIX = re.compile(r"^\s*([\w.-]+)\s*\|\s?(.*)$")


def _now():
    return datetime.now().strftime("%H:%M:%S")


def _find(o, key):
    if isinstance(o, dict):
        if key in o:
            return o[key]
        for v in o.values():
            r = _find(v, key)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find(v, key)
            if r is not None:
                return r
    return None


def emit(source, kind, verdict, detail):
    ev = {"ts": time.time(), "time": _now(), "source": source, "kind": kind, "verdict": verdict, "detail": detail}
    os.makedirs(os.path.dirname(EVENTS), exist_ok=True)
    with open(EVENTS, "a") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return ev


def show(ev):
    print("%s  %-8s %-7s %-9s %s" % (ev["time"], ev["source"], ev["kind"], ev["verdict"], ev["detail"]))
    sys.stdout.flush()


def log(source, kind, verdict, detail):
    show(emit(source, kind, verdict, detail))


def classify(line):
    s = line.rstrip("\n")
    m = PREFIX.match(s)
    body = m.group(2) if m else s
    if body.startswith("EGRESS "):
        rest = body[7:]
        if rest.startswith("ALLOW CONNECT"):
            return ("egress", "allow", "OK", rest.split(None, 2)[-1])
        if rest.startswith("DENY CONNECT"):
            return ("egress", "deny", "BLOCKED", "exfil blocked (https) " + rest.split(None, 2)[-1])
        if rest.startswith("DENY "):
            return ("egress", "deny", "BLOCKED", "exfil blocked (http) " + rest[5:])
        if rest.startswith("FAIL CONNECT"):
            return ("egress", "fail", "FLAG", rest)
        if rest.startswith("CAPTURE "):
            return ("egress", "capture", "CRITICAL", rest[8:])
        if rest.startswith("start "):
            return ("egress", "start", "INFO", rest)
    if body.startswith("CANARY-HIT "):
        payload = body[11:]
        try:
            d = json.loads(payload)
        except Exception:
            return ("canary", "hit", "CRITICAL", payload[:200])
        if d.get("event") == "canary_start":
            return ("canary", "start", "INFO", "canary up :%s" % d.get("port"))
        return ("canary", "hit", "CRITICAL", "internal probe %s body=%s" % (d.get("path"), (d.get("body") or "")[:160]))
    if body.startswith("[entrypoint]"):
        return ("openclaw", "boot", "INFO", body)
    return None


def run_stream():
    for line in sys.stdin:
        c = classify(line)
        if c:
            log(*c)


def run_agent():
    raw = sys.stdin.read()
    i = raw.find("{")
    obj = None
    if i >= 0:
        try:
            obj = json.loads(raw[i:])
        except Exception:
            obj = None
    if obj is None:
        log("agent", "error", "FLAG", "no parseable agent JSON")
        return
    trace = _find(obj, "executionTrace") or {}
    for a in (trace.get("attempts") or []):
        ok = a.get("result") == "success"
        log("agent", "step", "OK" if ok else "FLAG",
            "provider=%s model=%s stage=%s result=%s" % (a.get("provider"), a.get("model"), a.get("stage"), a.get("result")))
    text = _find(obj, "finalAssistantVisibleText") or ""
    emit("agent", "answer", "OK", text.replace("\n", " ")[:200])
    print("\n--- agent answer ---")
    print(text)


def _load(n=400):
    try:
        with open(EVENTS) as f:
            lines = f.readlines()[-n:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


def run_tail():
    for e in _load(200):
        show(e)


def run_exfil():
    caps = [e for e in _load(2000) if e.get("kind") in ("capture", "hit")]
    if not caps:
        print("no exfil captured yet.")
        return
    print("captured exfil / honeypot hits (nothing left the sandbox):")
    for e in caps:
        print("  %s  [%s/%s]  %s" % (e.get("time"), e.get("source"), e.get("verdict"), e.get("detail")))


def _render(evs):
    rows = []
    for e in reversed(evs):
        c = COLOR.get(e.get("verdict"), "#888")
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td style='color:%s;font-weight:600'>%s</td><td>%s</td></tr>" % (
            html.escape(e.get("time", "")), html.escape(e.get("source", "")), html.escape(e.get("kind", "")),
            c, html.escape(e.get("verdict", "")), html.escape(str(e.get("detail", "")))))
    caps = [e for e in evs if e.get("kind") in ("capture", "hit")][-10:]
    cap = "".join("<pre>%s</pre>" % html.escape(str(e.get("detail", ""))) for e in caps) or "<i>none yet</i>"
    return ("<!doctype html><html><head><meta charset=utf-8><meta http-equiv=refresh content=2>"
            "<title>OpenClaw lab monitor</title><style>"
            "body{font:13px/1.5 ui-monospace,monospace;background:#111;color:#ddd;margin:1rem}"
            "table{border-collapse:collapse;width:100%}td{padding:2px 8px;border-bottom:1px solid #222}"
            "h2{color:#9cf;margin:.6rem 0}.cap{background:#1a0d0d;border:1px solid #422;padding:.5rem;margin-bottom:1rem}"
            "pre{margin:.2rem 0;white-space:pre-wrap;color:#f88}</style></head><body>"
            "<h2>two-layer monitor &mdash; inner: OpenClaw &middot; outer: supervisor</h2>"
            "<div class=cap><b>captured exfil (honeypot)</b>%s</div>"
            "<h2>event stream</h2><table>%s</table></body></html>") % (cap, "".join(rows))


def run_serve():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    bind = os.environ.get("LAB_UI_BIND", "127.0.0.1")
    port = int(os.environ.get("LAB_UI_PORT", "8910"))

    class UI(BaseHTTPRequestHandler):
        def log_message(self, *a):
            return

        def do_GET(self):
            page = _render(_load(400)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

    print("dashboard: http://%s:%d" % (bind, port))
    print("from your laptop:  ssh -L %d:%s:%d <user>@<vm-ip>  then open http://localhost:%d" % (port, bind, port, port))
    ThreadingHTTPServer((bind, port), UI).serve_forever()


MODES = {"stream": run_stream, "agent": run_agent, "tail": run_tail, "exfil": run_exfil, "serve": run_serve}

if __name__ == "__main__":
    MODES.get(sys.argv[1] if len(sys.argv) > 1 else "stream", run_stream)()
