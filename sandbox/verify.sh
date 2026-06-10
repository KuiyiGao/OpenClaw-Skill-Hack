#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DC(){ docker compose -f "$HERE/docker-compose.yml" --env-file "$HERE/.env" exec -T openclaw bash -lc "$1"; }

echo "egress-lock self-test (inner agent's view):"
DC 'curl -s -o /dev/null -w "  LLM (allow)     %{http_code}\n" --max-time 12 https://api.deepseek.com/v1/models'
DC 'curl -s -o /dev/null -w "  exfil (deny)    %{http_code}\n" --max-time 8  https://example.com'
DC 'curl -s -o /dev/null -w "  metadata (deny) %{http_code}\n" --max-time 6  http://100.100.100.200/'
echo "expect: LLM 200/401 (reached), others 000 (blocked)"
