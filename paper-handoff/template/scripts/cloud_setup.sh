#!/usr/bin/env bash
# SessionStart hook: install the paper toolchain in Claude Code cloud containers only.
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

if ! command -v tectonic >/dev/null 2>&1; then
  (cd /usr/local/bin && curl -fsSL https://drop-sh.fullyjustified.net | sh) >/dev/null 2>&1 \
    || echo "tectonic install failed; check network policy" >&2
fi
python3 -m pip install -q matplotlib numpy pandas pytest 2>/dev/null || true
exit 0
