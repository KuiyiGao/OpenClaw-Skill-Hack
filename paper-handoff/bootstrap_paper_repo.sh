#!/usr/bin/env bash
# Turn the local ICLR paper folder into the AgentSkillsHack-ICLR-Paper repo and push it.
# Usage: [SEED=1] bash bootstrap_paper_repo.sh [PAPER_DIR] [REMOTE_URL]
# SEED=1 pushes only top-level notes, .handoff/ (transcripts, inventory) and tooling.
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
# Git must operate on PAPER_DIR itself, never on a parent repo it sits inside.
HERE_REAL="$(pwd -P)"
if [ "$(git rev-parse --show-toplevel 2>/dev/null)" != "$HERE_REAL" ]; then
  if [ -e .git ]; then
    echo "$HERE_REAL/.git exists but is not a valid repo (half-deleted?)." >&2
    echo "Make sure no git process is still running (pgrep -fl git), then: rm -rf \"$HERE_REAL/.git\" and re-run." >&2
    exit 1
  fi
  git init -q -b main
fi
[ "$(git rev-parse --show-toplevel)" = "$HERE_REAL" ] || { echo "git init failed in $HERE_REAL" >&2; exit 1; }
git remote get-url origin >/dev/null 2>&1 || git remote add origin "$REMOTE"
case "$(git remote get-url origin)" in
  *AgentSkillsHack-ICLR-Paper*) ;;
  *) echo "origin is $(git remote get-url origin), expected AgentSkillsHack-ICLR-Paper; refusing to push." >&2; exit 1;;
esac
if ! git ls-remote --exit-code --heads origin main >/dev/null 2>&1; then
  git update-ref -d HEAD 2>/dev/null || true
fi
git rm -r -q --cached . >/dev/null 2>&1 || true

# Inventory so the cloud session can decide what else belongs in the repo.
mkdir -p .handoff
{
  echo "# Workspace inventory ($(date +%F))"; echo
  echo "## Directories (depth 1-2, largest first): MB, files"; echo '```'
  find . -mindepth 1 -maxdepth 2 -type d -not -path './.git*' -not -path '*/external*' 2>/dev/null | while read -r d; do
    printf "%8d MB %7d files  %s\n" "$(( $(du -sk "$d" | cut -f1) / 1024 ))" "$(find "$d" -type f 2>/dev/null | wc -l)" "${d#./}"
  done | sort -rn | head -150
  echo '```'; echo
  echo "## Top-level files"; echo '```'; ls -la | grep -v '^d'; echo '```'; echo
  for r in $(ls -d iterations/*/ 2>/dev/null | sort | tail -4 | sed "s#/$##"); do
    echo "## $r (depth 2)"; echo '```'
    find "$r" -maxdepth 2 2>/dev/null | sort | head -120 | while read -r f; do
      if [ -d "$f" ]; then printf "%6d KB  %s/\n" "$(du -sk "$f" | cut -f1)" "$f"; else printf "%6d KB  %s\n" "$(( ($(wc -c < "$f") + 1023) / 1024 ))" "$f"; fi
    done
    echo '```'; echo
  done
  echo "## Bytes by extension (whole workspace, excluding external/)"; echo '```'
  find . -type f -not -path './.git/*' -not -path '*/external/*' -print0 2>/dev/null | xargs -0 du -k 2>/dev/null \
    | awk '{f=$2; for(i=3;i<=NF;i++) f=f" "$i; n=split(f,p,"/"); b=p[n]; k=split(b,q,"."); e=(k>1)?q[k]:"(none)"; s[e]+=$1; c[e]++} END {for (e in s) printf "%8d MB %7d files  .%s\n", s[e]/1024, c[e], e}' | sort -rn | head -40
  echo '```'
} > .handoff/INVENTORY.md
echo "wrote .handoff/INVENTORY.md"

if [ "${SEED:-0}" = 1 ]; then
  # First push: notes, transcripts, inventory, tooling only.
  find . -maxdepth 1 -type f -size -5M -not -name '.DS_Store' -print0 | xargs -0 git add --
  for p in .handoff .claude scripts .github; do [ -e "$p" ] && git add -- "$p"; done
else
  git add -A
fi

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
