#!/usr/bin/env bash
set -euo pipefail

: "${LLM_API_KEY:?LLM_API_KEY is required (set it in sandbox/.env)}"
LLM_MODEL="${LLM_MODEL:-deepseek-chat}"
LLM_BASE_URL="${LLM_BASE_URL:-https://api.deepseek.com/v1}"
LLM_API="${LLM_API:-openai-completions}"

mkdir -p "$HOME/.openclaw/workspace/skills"

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
        "models": [{"id": os.environ["LLM_MODEL"], "name": os.environ["LLM_MODEL"], "api": os.environ["LLM_API"]}],
      }
    }
  }
}
json.dump(cfg, open(cfg_path, "w"), indent=2)
print(f"[entrypoint] wrote {cfg_path} provider=real model={os.environ['LLM_MODEL']} base={os.environ['LLM_BASE_URL']}")
PY

exec "$@"
