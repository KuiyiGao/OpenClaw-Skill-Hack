#!/usr/bin/env bash
# Turn the local ICLR paper folder into the AgentSkillsHack-ICLR-Paper repo and push it.
# Usage: bash bootstrap_paper_repo.sh [PAPER_DIR] [REMOTE_URL]
set -euo pipefail

PAPER_DIR="${1:-$HOME/Codes/AgentSkillsHack/iclr}"
REMOTE="${2:-git@github.com:KuiyiGao/AgentSkillsHack-ICLR-Paper.git}"
HERE="$(cd "$(dirname "$0")" && pwd)"

[ -d "$PAPER_DIR" ] || { echo "no such dir: $PAPER_DIR" >&2; exit 1; }
cd "$PAPER_DIR"

# Copy template files, never overwriting existing ones.
(cd "$HERE/template" && find . -type f) | while read -r f; do
  if [ -e "$f" ]; then echo "keep existing  $f"; else
    mkdir -p "$(dirname "$f")"; cp "$HERE/template/$f" "$f"; echo "added          $f"; fi
done
chmod +x scripts/*.sh 2>/dev/null || true

echo; echo "Files over 50 MB (GitHub rejects >100 MB; consider .gitignore or LFS):"
find . -path ./.git -prune -o -type f -size +50M -print | sed 's/^/  /' || true
echo

[ -d .git ] || git init -b main
git add -A
git -c core.hooksPath=/dev/null commit -m "Import ICLR paper workspace from Mac for cloud iteration" || echo "(nothing new to commit)"
git remote get-url origin >/dev/null 2>&1 || git remote add origin "$REMOTE"
git push -u origin HEAD:main
echo; echo "Pushed. Start a cloud session on KuiyiGao/AgentSkillsHack-ICLR-Paper."
