#!/usr/bin/env python3
"""Run every skill in a folder through the firewall and print one CSV row each.

Usage::

    python experiment_minimal/run.py path/to/skills/ [--log-dir runs/]

The script does NOT install the skill into any agent. It scans each skill
folder statically and, if a per-skill log file exists (e.g. produced by a
prior live run), replays it through the L2 verifier. The CSV format is::

    skill_name, static_severity, runtime_verdict, runtime_score, reason
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from firewall.config import load_config
from firewall.gate.static_scanner import scan_skill_dir
from firewall.runtime.firewall import analyze_iar, build_intent_envelope
from firewall.runtime.supervisor import evidence_from_events, parse_line
from firewall.skills.discover import load_skill


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("skills_root", type=Path,
                   help="folder containing skill subdirs (each with SKILL.md)")
    p.add_argument("--log-dir", type=Path, default=None,
                   help="folder with per-skill .log files (NAME.log -> evidence)")
    p.add_argument("--out", type=Path, default=Path("-"),
                   help="output CSV path (default: stdout)")
    args = p.parse_args(argv)

    cfg = load_config()
    if not args.skills_root.is_dir():
        print(f"not a dir: {args.skills_root}", file=sys.stderr)
        return 2

    out_fh = sys.stdout if str(args.out) == "-" else args.out.open("w")
    writer = csv.writer(out_fh)
    writer.writerow(["skill", "static_severity", "runtime_verdict",
                     "runtime_score", "reason"])

    for child in sorted(args.skills_root.iterdir()):
        if not child.is_dir():
            continue
        sk = load_skill(child)
        if sk is None:
            continue
        static = scan_skill_dir(child, cfg)
        static_sev = static[0].severity if static else "NONE"

        runtime_verdict = "—"
        score = 0
        reason = "no log"
        if args.log_dir:
            log_path = args.log_dir / f"{sk.name}.log"
            if log_path.exists():
                events = [parse_line(line) for line in log_path.read_text().splitlines()]
                events = [e for e in events if e is not None]
                evidence = evidence_from_events(events)
                envelope = build_intent_envelope(sk.to_intent())
                v = analyze_iar(evidence, envelope, cfg)
                runtime_verdict = v.verdict
                score = v.score
                reason = ", ".join(v.confirmations or v.divergences)[:80] or "-"

        writer.writerow([sk.name, static_sev, runtime_verdict, score, reason])

    if out_fh is not sys.stdout:
        out_fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
