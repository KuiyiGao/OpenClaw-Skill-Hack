#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"
CF="$HERE/docker-compose.yml"; cd "$ROOT"
dc() { docker compose -f "$CF" --env-file "$HERE/.env" "$@"; }

cmd="${1:-list}"; shift || true
case "$cmd" in
  list)
    dc exec -T openclaw openclaw skills list ;;
  scan)
    dir="${1:?usage: skillctl.sh scan <dir>}"
    echo "gate severity = $("$HERE/gate.sh" "$dir")" ;;
  add)
    dir="${1:?usage: skillctl.sh add <dir> [--force]}"; force="${2:-}"
    sev="$("$HERE/gate.sh" "$dir")"
    echo "gate severity = $sev"
    if [ "$force" != "--force" ] && { [ "$sev" = HIGH ] || [ "$sev" = CRITICAL ] || [ "$sev" = ERR ]; }; then
      echo "Rejected by gate. Re-run with --force to install anyway."; exit 1
    fi
    abs="$(cd "$dir" && pwd)"
    dc run --rm -v "$abs":/work/skill:ro openclaw \
       openclaw skills install /work/skill --global --force
    echo "Installed ($(basename "$abs"))" ;;
  rm)
    slug="${1:?usage: skillctl.sh rm <slug>}"
    dc exec -T openclaw openclaw skills remove "$slug" 2>/dev/null \
      || dc exec -T openclaw openclaw skills uninstall "$slug" ;;
  *)
    echo "unknown command: $cmd (list|scan|add|rm)"; exit 1 ;;
esac
