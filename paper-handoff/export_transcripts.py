#!/usr/bin/env python3
"""Export local Claude Code transcripts for this project into readable Markdown.

Claude Code keeps every CLI / Remote Control session on the Mac under
~/.claude/projects/<encoded-cwd>/<session>.jsonl. Cloud sessions cannot read
them, so this condenses them (your messages, Claude's replies, a one-line note
per tool call; tool outputs dropped; obvious secrets redacted) into
<PAPER_DIR>/.handoff/transcripts/ so the cloud session can pick up the thread.

Usage: python3 export_transcripts.py [PAPER_DIR] [--match AgentSkillsHack] [--since 2026-09-01]
"""
import argparse, json, os, re, sys
from datetime import datetime
from pathlib import Path

SECRET = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|sk-ant-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,}|xox[baprs]-[A-Za-z0-9\-]{10,}"
    r"|(?i:(?:api[_-]?key|token|secret|password)\s*[=:]\s*)['\"]?[^\s'\"]{8,})"
)

def redact(s): return SECRET.sub("[REDACTED]", s)

def blocks(content):
    if isinstance(content, str):
        yield "text", content
        return
    for b in content or []:
        t = b.get("type")
        if t == "text": yield "text", b.get("text", "")
        elif t == "tool_use":
            inp = b.get("input") or {}
            hint = inp.get("command") or inp.get("file_path") or inp.get("pattern") or inp.get("description") or ""
            yield "tool", f"{b.get('name')}: {str(hint).splitlines()[0][:160] if hint else ''}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paper_dir", nargs="?", default=os.path.expanduser("~/Codes/AgentSkillsHack/iclr"))
    ap.add_argument("--match", default="AgentSkillsHack")
    ap.add_argument("--since", default="2026-09-01")
    a = ap.parse_args()
    since = datetime.fromisoformat(a.since).timestamp()
    root = Path.home() / ".claude" / "projects"
    out = Path(a.paper_dir) / ".handoff" / "transcripts"
    out.mkdir(parents=True, exist_ok=True)

    files = [p for d in root.iterdir() if d.is_dir() and a.match.lower() in d.name.lower()
             for p in d.glob("*.jsonl") if p.stat().st_mtime >= since]
    files.sort(key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit(f"no transcripts under {root} matching '{a.match}' since {a.since}")

    index = ["# Exported transcripts (oldest first)", "",
             "| File | Last activity | Turns | Folder | First message |", "|---|---|---|---|---|"]
    for p in files:
        lines, turns, first, cwd, summary = [], 0, "", "", ""
        for raw in p.open(encoding="utf-8", errors="replace"):
            try: e = json.loads(raw)
            except json.JSONDecodeError: continue
            if e.get("type") == "summary": summary = e.get("summary", ""); continue
            if e.get("type") not in ("user", "assistant") or e.get("isMeta"): continue
            cwd = cwd or e.get("cwd", "")
            msg = e.get("message") or {}
            ts = (e.get("timestamp") or "")[:16].replace("T", " ")
            for kind, txt in blocks(msg.get("content")):
                txt = redact(txt.strip())
                if not txt or txt.startswith("<command-") or txt.startswith("<local-command"): continue
                if kind == "tool":
                    lines.append(f"- `{txt}`")
                elif e["type"] == "user":
                    turns += 1
                    first = first or txt.splitlines()[0][:80]
                    lines.append(f"\n## USER · {ts}\n\n{txt}\n")
                else:
                    lines.append(f"\n**CLAUDE** · {ts}\n\n{txt}\n")
        name = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y%m%d-%H%M") + f"-{p.stem[:8]}.md"
        (out / name).write_text(f"# Session {p.stem}\n\nFolder: `{cwd}`\n\n{('Summary: ' + summary) if summary else ''}\n" + "\n".join(lines), encoding="utf-8")
        index.append(f"| [{name}]({name}) | {datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M} | {turns} | `{cwd}` | {first.replace('|', '/')} |")
        print(f"{name}  {turns} turns  {os.path.getsize(out / name)//1024} KB")
    (out / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"\nwrote {len(files)} transcripts to {out}")

if __name__ == "__main__":
    main()
