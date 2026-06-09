#!/usr/bin/env bash
# Monitoring entry point: stream OpenClaw output, canary tripwire hits, and blocked egress attempts.
#   ./sandbox/monitor.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CF="$HERE/docker-compose.yml"
echo "Watch for: CANARY-HIT (induced exfil) and EGRESS DENY (blocked outbound). Ctrl-C to exit."
exec docker compose -f "$CF" --env-file "$HERE/.env" logs -f openclaw canary egress-proxy
