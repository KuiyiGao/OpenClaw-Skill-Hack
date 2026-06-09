#!/usr/bin/env bash
# 最强隔离的一次性运行：零出网 + 非 root + 只读根 + 丢弃能力。
# 用于"安全引爆"——跑离线攻防 demo / canary 技能，主机绝不进入循环。
#
#   ./sandbox/run_sandbox.sh                      # 跑 run_demo.py（默认）
#   ./sandbox/run_sandbox.sh python -m pytest tests/ -q
#   IMAGE=asshack-sandbox:latest ./sandbox/run_sandbox.sh bash   # 进容器排查
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
IMAGE="${IMAGE:-asshack-sandbox:latest}"

if ! command -v docker >/dev/null 2>&1; then
  echo "需要 docker。请在隔离环境（或一次性云 VM）中安装后再运行。" >&2
  exit 1
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "[build] $IMAGE ..."
  docker build -f "$HERE/Dockerfile" -t "$IMAGE" "$ROOT"
fi

if [ "$#" -eq 0 ]; then
  set -- python scripts/run_demo.py
fi

# --network none：彻底无网络，连内网都没有 → 适合纯离线引爆
exec docker run --rm \
  --network none \
  --user 65532:65532 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 256 \
  --memory 768m --cpus 1 \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$IMAGE" "$@"
