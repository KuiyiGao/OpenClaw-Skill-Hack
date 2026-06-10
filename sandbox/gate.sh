#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
dir="${1:?usage: gate.sh <skill_dir>}"

MODE="${GATE_MODE:-}"
[ -z "$MODE" ] && MODE="$(grep -E '^GATE_MODE=' "$HERE/.env" 2>/dev/null | head -1 | cut -d= -f2)"
MODE="${MODE:-scan}"

case "$MODE" in
  off)    echo "NONE" ;;
  custom) "$HERE/gate_custom.sh" "$dir" ;;
  scan)   "$HERE/cisco_scan.sh" "$dir" ;;
  *)      echo "ERR" ;;
esac
