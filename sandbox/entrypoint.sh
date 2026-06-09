#!/usr/bin/env bash
# OpenClaw 容器入口：用 .env 注入的真实 LLM 生成 ~/.openclaw/openclaw.json，然后常驻。
# 不写任何多余 secret；apiKey 只来自 LLM_API_KEY。
set -euo pipefail

: "${LLM_API_KEY:?需要 LLM_API_KEY（在 sandbox/.env 设置）}"
LLM_MODEL="${LLM_MODEL:-gpt-4o-mini}"
LLM_BASE_URL="${LLM_BASE_URL:-https://api.openai.com/v1}"
LLM_API="${LLM_API:-openai-responses}"

mkdir -p "$HOME/.openclaw/workspace/skills"

# 每次启动用 .env 重新生成模型配置；已装技能在持久化卷里保留（重启不丢）
CFG="$HOME/.openclaw/openclaw.json"
LLM_MODEL="$LLM_MODEL" LLM_BASE_URL="$LLM_BASE_URL" LLM_API="$LLM_API" \
python3 - "$CFG" <<'PY'
import json, os, sys
cfg_path = sys.argv[1]
cfg = {
  "models": {
    "providers": {
      "real": {
        "baseUrl": os.environ["LLM_BASE_URL"],
        "apiKey": os.environ["LLM_API_KEY"],
        "auth": "api-key",
        "api": os.environ["LLM_API"],
        # 出网经环境变量代理（HTTPS_PROXY=egress-proxy）→ 只放行允许列表，无需在配置里再写
        "models": [{"id": os.environ["LLM_MODEL"], "name": os.environ["LLM_MODEL"], "api": os.environ["LLM_API"]}],
      }
    }
  }
}
json.dump(cfg, open(cfg_path, "w"), indent=2)
print(f"[entrypoint] wrote {cfg_path}  provider=real model={os.environ['LLM_MODEL']} base={os.environ['LLM_BASE_URL']}")
PY

exec "$@"
