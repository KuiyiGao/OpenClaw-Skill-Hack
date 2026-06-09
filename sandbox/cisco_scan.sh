#!/usr/bin/env bash
# 预留的 Cisco 扫描接口（静态分析，--network none，不执行被扫技能）。
#   ./sandbox/cisco_scan.sh <skill_dir>
# 输出该技能的 max_severity：NONE/INFO/LOW/MEDIUM/HIGH/CRITICAL；扫描失败=ERR；扫描器不可用=SKIP。
# “保证能用就行”：镜像缺失时尝试构建；构建不了返回 SKIP（接口保留，不阻断流程）。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"
dir="${1:?用法: cisco_scan.sh <skill_dir>}"; abs="$(cd "$dir" && pwd)"
IMG="${SCANNER_IMAGE:-asshack-scanner:latest}"

command -v docker >/dev/null || { echo "SKIP"; exit 0; }
if ! docker image inspect "$IMG" >/dev/null 2>&1; then
  docker image inspect asshack-sandbox:latest >/dev/null 2>&1 \
    || docker build -f "$ROOT/sandbox/Dockerfile" -t asshack-sandbox:latest "$ROOT" >/dev/null 2>&1 || true
  docker build -f "$ROOT/sandbox/Dockerfile.scanner" -t "$IMG" "$ROOT" >/dev/null 2>&1 \
    || { echo "SKIP"; exit 0; }
fi

json="$(docker run --rm --network none -e HOME=/tmp --read-only --tmpfs /tmp:size=128m \
        --user 65532:65532 --cap-drop ALL --security-opt no-new-privileges \
        -v "$abs":/skill:ro "$IMG" \
        skill-scanner scan /skill --use-behavioral --format json 2>/dev/null || true)"
printf '%s' "$json" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("max_severity","NONE"))
except Exception: print("ERR")'
