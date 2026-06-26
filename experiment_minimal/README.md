# Experiment harness (minimal)

A tiny, self-contained driver for running your own skills against the
firewall and seeing the per-case verdict — without the larger research
console, the MalSkillBench loader, or any stored datasets.

## What's here

* `run.py` — loop over a folder of skills, run each through
  `firewall scan` (L0 static) and `firewall watch` (L2 runtime, against
  a per-case log if you have one), and write a one-line CSV result.
* `panel.html` (v2 console) — a *very* small browser dashboard that
  reads `~/Library/Application Support/firewall/events.jsonl` (or the
  XDG equivalent) and renders the same passed/blocked table the TUI
  shows. Use this when a browser is preferred over the terminal.

## Usage

```bash
# 1. Bring up the firewall in another terminal
firewall start

# 2. Point this script at your skill folder (any layout that contains
#    SKILL.md folders works — see `firewall skills`)
python experiment_minimal/run.py path/to/skills/ > results.csv

# 3. Open the dashboard, or use `firewall panel`
python -m http.server -d experiment_minimal/ 8090
#   then visit http://127.0.0.1:8090/panel.html
```

## What was removed

The old research console (`sandbox/console.py` + `sandbox/console.html`)
remains available in `console_archive/` as a frozen reference. It was
tied to MalSkillBench loaders, a Docker harness, and the stored research
runs — none of which ship with the public package. The minimal harness
here covers the same workflow without the dataset baggage.
