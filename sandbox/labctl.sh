#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"
CF="$HERE/docker-compose.yml"; ENVF="$HERE/.env"
export LAB_EVENTS="$HERE/_events/events.jsonl"
DC(){ docker compose -f "$CF" --env-file "$ENVF" "$@"; }

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
    if grep -q '^GATE_MODE=' "$ENVF" 2>/dev/null; then
      sed -i "s/^GATE_MODE=.*/GATE_MODE=$val/" "$ENVF"
    else
      echo "GATE_MODE=$val" >> "$ENVF"
    fi
    echo "gate mode = $val" ;;
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
