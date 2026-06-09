#!/usr/bin/env bash
# 监控入口：实时查看 OpenClaw 的反应、canary tripwire 命中、以及被代理拦截的外泄尝试。
#   ./sandbox/monitor.sh
# 你据此判断该启用/停用哪些技能（配合 skillctl.sh）。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CF="$HERE/docker-compose.yml"
echo "== 监控 OpenClaw / canary / egress-proxy（Ctrl-C 退出）=="
echo "   关注：CANARY-HIT（被诱导的外泄尝试）、squid TCP_DENIED（被拦截的出网）"
exec docker compose -f "$CF" --env-file "$HERE/.env" logs -f openclaw canary egress-proxy
