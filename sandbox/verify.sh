#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DC(){ docker compose -f "$HERE/docker-compose.yml" --env-file "$HERE/.env" exec -T openclaw bash -lc "$1"; }
code(){ DC "curl -s -o /dev/null -w '%{http_code}' --max-time ${2:-8} '$1'"; }

echo "egress-lock self-test (inner agent's view):"
c=$(code https://api.deepseek.com/v1/models 12)
{ [ "$c" = 200 ] || [ "$c" = 401 ]; } && r=PASS || r=CHECK
echo "  LLM domain        $c   $r (reached -- real key -> 200)"
c=$(code https://example.com 8)
[ "$c" = 000 ] && r=PASS || r=FAIL
echo "  arbitrary https   $c   $r (CONNECT denied)"
c=$(code http://100.100.100.200/ 6)
[ "$c" != 200 ] && r=PASS || r=FAIL
echo "  cloud metadata    $c   $r (non-public hard-denied)"
