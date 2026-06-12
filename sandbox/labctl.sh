#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"
CF="$HERE/docker-compose.yml"; ENVF="$HERE/.env"
export LAB_EVENTS="$HERE/_events/events.jsonl"
DC(){ docker compose -f "$CF" --env-file "$ENVF" "$@"; }
_getenv(){ grep -E "^$1=" "$ENVF" 2>/dev/null | head -1 | cut -d= -f2-; }
_setenv(){ if grep -qE "^$1=" "$ENVF" 2>/dev/null; then tmp="$(mktemp)"; sed "s|^$1=.*|$1=$2|" "$ENVF" > "$tmp" && mv "$tmp" "$ENVF"; else echo "$1=$2" >> "$ENVF"; fi; }

cmd="${1:-help}"; shift || true
case "$cmd" in
  up)
    test -f "$ENVF" || { echo "first: cp $HERE/.env.example $ENVF and set LLM_API_KEY"; exit 1; }
    DC up -d >/dev/null && echo "lab up: egress-proxy + canary + openclaw" ;;
  down)
    DC down >/dev/null && echo "lab down (skills + config persist in the volume)" ;;
  ask)
    msg="${*:-Introduce yourself in one sentence.}"
    DC exec -T openclaw bash -lc "openclaw agent --local --model real/\$LLM_MODEL \
      --session-key agent:lab:1 --message \"$msg\" --json" 2>/dev/null \
      | python3 "$HERE/supervisor.py" agent ;;
  watch)
    DC logs -f --tail=0 egress-proxy canary openclaw | python3 "$HERE/supervisor.py" stream ;;
  ui)
    python3 "$HERE/supervisor.py" serve ;;
  exfil)
    python3 "$HERE/supervisor.py" exfil ;;
  events)
    python3 "$HERE/supervisor.py" tail ;;
  gate)
    val="${1:?usage: labctl.sh gate <off|scan|custom>}"
    case "$val" in off|scan|custom) ;; *) echo "gate mode must be off|scan|custom"; exit 1 ;; esac
    _setenv GATE_MODE "$val"
    echo "gate mode = $val" ;;
  provider)
    val="${1:?usage: labctl.sh provider <deepseek|k2>}"
    case "$val" in deepseek|k2) ;; *) echo "provider must be deepseek|k2"; exit 1 ;; esac
    P="$(echo "$val" | tr a-z A-Z)"
    k="$(_getenv ${P}_API_KEY)"; m="$(_getenv ${P}_MODEL)"; b="$(_getenv ${P}_BASE_URL)"
    a="$(_getenv ${P}_API)"; e="$(_getenv ${P}_EGRESS)"
    { [ -n "$k" ] && [ -n "$b" ] && [ -n "$m" ]; } || { echo "profile ${P}_* incomplete in $ENVF"; exit 1; }
    _setenv PROVIDER "$val"; _setenv LLM_API_KEY "$k"; _setenv LLM_MODEL "$m"
    _setenv LLM_BASE_URL "$b"; _setenv LLM_API "$a"; _setenv EGRESS_ALLOW "$e"
    case "$k" in sk-REPLACE_ME|"") echo "note: ${P}_API_KEY is still a placeholder -- set it in $ENVF" ;; esac
    echo "provider = $val (model=$m egress=$e). apply: make oc-down && make oc-up" ;;
  skill)
    sub="${1:?usage: labctl.sh skill <list|scan|add|rm> [args]}"; shift || true
    "$HERE/skillctl.sh" "$sub" "$@" ;;
  verify)
    "$HERE/verify.sh" ;;
  help|*)
    cat <<'H'
labctl - OpenClaw research lab control surface

lifecycle
  up                        start the lab
  down                      stop the lab

inner layer (the agent)
  ask "<message>"           ask OpenClaw; prints clean answer + per-step trace

outer layer (the supervisor / your judgment)
  watch                     live judged event stream (egress / canary / boot)
  ui                        web dashboard on 127.0.0.1:8910 (SSH-tunnel to view)
  exfil                     show captured exfil payloads (honeypot)
  events                    replay recorded events

model provider (switching strategy)
  provider deepseek|k2      switch active LLM provider + egress; then make oc-down && oc-up
                            (k2 = Kimi K2 via ifm.ai; fill K2_* in .env from https://ifm.ai/docs)

gate (pre-load filter, your call)
  gate off|scan|custom      off = no filter; scan = Cisco; custom = sandbox/gate_custom.sh
  skill list                installed skills
  skill scan <dir>          scan only, print severity
  skill add  <dir> [--force] install via the gate (--force overrides)
  skill rm   <slug>         remove a skill

safety
  verify                    egress-lock self-test (allow LLM, deny everything else)
H
    ;;
esac
