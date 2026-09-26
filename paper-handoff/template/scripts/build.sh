#!/usr/bin/env bash
# Compile the paper. Default: the main .tex in the newest iterations/ round.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEX="${1:-}"
if [ -z "$TEX" ]; then
  ROUND="$(ls -d "$ROOT"/iterations/*/ 2>/dev/null | sort | tail -1)"
  [ -n "$ROUND" ] || { echo "no iterations/ round found" >&2; exit 1; }
  TEX="$(grep -l '\\documentclass' "$ROUND"*.tex "$ROUND"*/*.tex 2>/dev/null | head -1)"
fi
[ -f "$TEX" ] || { echo "main .tex not found" >&2; exit 1; }
cd "$(dirname "$TEX")"
if command -v tectonic >/dev/null 2>&1; then tectonic -X compile "$(basename "$TEX")"
else latexmk -pdf -interaction=nonstopmode "$(basename "$TEX")"; fi
echo "built: $(dirname "$TEX")/$(basename "${TEX%.tex}").pdf"
