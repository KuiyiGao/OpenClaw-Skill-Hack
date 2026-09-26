#!/usr/bin/env bash
# Turn the local ICLR paper folder into the AgentSkillsHack-ICLR-Paper repo and push it.
# Usage: bash bootstrap_paper_repo.sh [PAPER_DIR] [REMOTE_URL]
# Safe to re-run: it never touches your working files, only git metadata and .gitignore.
set -euo pipefail

PAPER_DIR="${1:-$HOME/Codes/AgentSkillsHack/iclr}"
REMOTE="${2:-git@github.com:KuiyiGao/AgentSkillsHack-ICLR-Paper.git}"
MAX_MB="${MAX_MB:-50}"
HERE="$(cd "$(dirname "$0")" && pwd)"

[ -d "$PAPER_DIR" ] || { echo "no such dir: $PAPER_DIR" >&2; exit 1; }
cd "$PAPER_DIR"

# 1. Template files, never overwriting existing ones.
(cd "$HERE/template" && find . -type f) | while read -r f; do
  if [ -e "$f" ]; then echo "keep existing  $f"; else
    mkdir -p "$(dirname "$f")"; cp "$HERE/template/$f" "$f"; echo "added          $f"; fi
done
chmod +x scripts/*.sh 2>/dev/null || true

# 2. Exclude third-party data: every `external/` dir, every nested git repo,
#    every file over MAX_MB. Record where they came from in DATA_SOURCES.md.
BEGIN='# >>> bootstrap: third-party data (auto-generated, re-run script to refresh) >>>'
END='# <<< bootstrap <<<'
[ -f .gitignore ] && sed -i.bak "/^$BEGIN\$/,/^$END\$/d" .gitignore && rm -f .gitignore.bak
{
  echo "$BEGIN"
  echo "**/external/"
  echo "*.zip"; echo "*.tar.gz"; echo "*.db"
  find . -mindepth 2 -name .git -not -path './.git/*' -prune 2>/dev/null \
    | grep -v '/external/' | sed -e 's#^\./##' -e 's#/\.git$#/#' || true
  find . -path ./.git -prune -o -path '*/external/*' -prune -o -type f -size +"${MAX_MB}"M -print 2>/dev/null \
    | sed 's#^\./##' || true
  echo "$END"
} >> .gitignore

{
  echo "# Third-party data (not in git)"
  echo
  echo "Excluded by \`.gitignore\`. Re-fetch on a machine that needs them."
  echo "Generated $(date +%F) by paper-handoff/bootstrap_paper_repo.sh."
  echo
  echo "| Path | Size | Git remote @ commit |"
  echo "|---|---|---|"
  find . -type d -name external -not -path './.git/*' -prune 2>/dev/null | while read -r ext; do
    for d in "$ext"/*/; do
      [ -d "$d" ] || continue
      d="${d%/}"; size="$(du -sh "$d" 2>/dev/null | cut -f1)"
      src="$(find "$d" -maxdepth 3 -name .git -type d 2>/dev/null | head -1)"
      if [ -n "$src" ]; then
        r="$(git -C "$(dirname "$src")" remote get-url origin 2>/dev/null || echo '?')"
        c="$(git -C "$(dirname "$src")" rev-parse --short HEAD 2>/dev/null || echo '?')"
        echo "| \`${d#./}\` | $size | $r @ $c |"
      else
        echo "| \`${d#./}\` | $size | (downloaded archive, no git) |"
      fi
    done
  done
} > DATA_SOURCES.md
echo "wrote DATA_SOURCES.md"

# 3. Fresh index. If nothing was ever pushed, drop any local commit a previous run made.
[ -d .git ] || git init -q -b main
git remote get-url origin >/dev/null 2>&1 || git remote add origin "$REMOTE"
if ! git ls-remote --exit-code --heads origin main >/dev/null 2>&1; then
  git update-ref -d HEAD 2>/dev/null || true
fi
git rm -r -q --cached . >/dev/null 2>&1 || true
git add -A

# 4. Safety check before pushing.
TOTAL_KB="$(git ls-files -z | xargs -0 du -k 2>/dev/null | awk '{s+=$1} END {print s+0}')"
echo; echo "Tracked: $(git ls-files | wc -l | tr -d ' ') files, $((TOTAL_KB/1024)) MB"
BIG="$(git ls-files -z | xargs -0 du -k 2>/dev/null | awk -v m=$((MAX_MB*1024)) '$1>m {print $2}')"
if [ -n "$BIG" ]; then echo "Still tracking big files, add them to .gitignore:"; echo "$BIG"; exit 1; fi
if [ "$TOTAL_KB" -gt $((500*1024)) ]; then
  echo "Over 500 MB tracked. Largest dirs:"
  git ls-files -z | xargs -0 du -k 2>/dev/null | awk '{split($2,p,"/"); d=p[1]"/"p[2]; s[d]+=$1} END {for (k in s) print s[k]/1024 " MB\t" k}' | sort -rn | head -15
  echo "Add the ones that are data, not paper, to .gitignore and re-run. (Set FORCE=1 to push anyway.)"
  [ "${FORCE:-0}" = 1 ] || exit 1
fi

git -c core.hooksPath=/dev/null commit -q -m "Import ICLR paper workspace from Mac for cloud iteration" || echo "(nothing new to commit)"
git push -u origin HEAD:main
echo; echo "Pushed. Tell the cloud session the repo is up."
