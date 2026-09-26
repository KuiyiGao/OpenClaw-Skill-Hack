# Paper handoff: move the ICLR paper off the Mac and into the cloud

The earlier "ICLR论文细分与实验补全" sessions ran over Remote Control against
`~/Codes/AgentSkillsHack/iclr/` on the Mac. That folder was never pushed to
GitHub, so cloud sessions could not see it: two cloud sessions on 2026-09-26
(the fixture schema v1/v1.1 fix and the Times-font figure rebuild) stopped
with "repo not found".

This kit turns that folder into its own private repo, `AgentSkillsHack-ICLR-Paper`,
that cloud sessions can build, iterate on and push to.

## Steps (on the Mac, about 2 minutes)

1. Create an **empty private** repo on GitHub named `AgentSkillsHack-ICLR-Paper`
   (no README, no .gitignore): https://github.com/new
   The Claude integration cannot create repos for you (GitHub returns 403).
2. Make sure the Claude GitHub App can reach it:
   https://github.com/apps/claude/installations/select_target → add the repo
   (skip if the app is installed on all repos).
3. Run:
   ```bash
   cd ~/Codes/AgentSkillsHack/OpenClaw-Skill-Hack   # or wherever this repo is cloned
   git fetch origin claude/gallant-volta-9uta63
   git checkout origin/claude/gallant-volta-9uta63 -- paper-handoff
   bash paper-handoff/bootstrap_paper_repo.sh ~/Codes/AgentSkillsHack/iclr
   ```
   The script copies the template files in (without overwriting anything you
   already have), lists files over 50 MB so you can decide on them, makes the
   first commit and pushes to `main`.
4. Start a cloud session on `KuiyiGao/AgentSkillsHack-ICLR-Paper` and say
   "继续论文" — `CLAUDE.md` and `HANDOFF.md` in the repo tell it where things
   stand. Or tell this session the repo is up and it will attach it.

## What the template adds

| File | Purpose |
|---|---|
| `CLAUDE.md` | Working rules for cloud sessions: layout, build, iteration protocol, honesty bar |
| `HANDOFF.md` | Open tasks carried over from the Mac sessions; fill in the blanks before pushing |
| `.claude/settings.json` + `scripts/cloud_setup.sh` | SessionStart hook: installs tectonic + Python deps in the cloud container |
| `scripts/build.sh` | One command to compile the PDF (tectonic, falls back to latexmk) |
| `.github/workflows/build-pdf.yml` | CI compiles every push and uploads the PDF as an artifact |
| `.gitignore` | LaTeX aux files, caches, raw run logs |
