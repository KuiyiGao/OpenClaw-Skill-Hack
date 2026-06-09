#!/usr/bin/env bash
# 技能控制台：由你决定 OpenClaw 能用哪些技能（Cisco 扫描门 + 显式批准）。
#   ./sandbox/skillctl.sh list                 列出 OpenClaw 已装技能
#   ./sandbox/skillctl.sh scan <dir>           只扫描，给出 Cisco 严重度
#   ./sandbox/skillctl.sh add  <dir>           扫描→干净才装入（HIGH/CRITICAL 拒绝）
#   ./sandbox/skillctl.sh add  <dir> --force   你明确批准，强制装入（科研用）
#   ./sandbox/skillctl.sh rm   <slug>          移除技能
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"
CF="$HERE/docker-compose.yml"; cd "$ROOT"
dc() { docker compose -f "$CF" --env-file "$HERE/.env" "$@"; }

cmd="${1:-list}"; shift || true
case "$cmd" in
  list)
    dc exec -T openclaw openclaw skills list ;;
  scan)
    dir="${1:?用法: skillctl.sh scan <dir>}"
    echo "Cisco max_severity = $("$HERE/cisco_scan.sh" "$dir")" ;;
  add)
    dir="${1:?用法: skillctl.sh add <dir> [--force]}"; force="${2:-}"
    sev="$("$HERE/cisco_scan.sh" "$dir")"
    echo "Cisco max_severity = $sev"
    if [ "$force" != "--force" ] && { [ "$sev" = HIGH ] || [ "$sev" = CRITICAL ] || [ "$sev" = ERR ]; }; then
      echo "✗ 拒绝装入（扫描门阻断）。如确需，追加 --force 由你明确批准。"; exit 1
    fi
    abs="$(cd "$dir" && pwd)"
    dc run --rm -v "$abs":/work/skill:ro openclaw \
       openclaw skills install /work/skill --global --force
    echo "✓ 已装入（$(basename "$abs")）" ;;
  rm)
    slug="${1:?用法: skillctl.sh rm <slug>}"
    dc exec -T openclaw openclaw skills remove "$slug" 2>/dev/null \
      || dc exec -T openclaw openclaw skills uninstall "$slug" ;;
  *)
    echo "未知命令: $cmd（list|scan|add|rm）"; exit 1 ;;
esac
