# Usage

Run real OpenClaw in an isolated sandbox against a real LLM (DeepSeek by default), with a
two-layer setup: an **inner** agent you talk to, and an **outer** supervisor that observes
every event, assigns a verdict, and lets you judge. Egress is locked so the agent (and any
skill it loads) cannot reach your credentials or cloud metadata.

See `INTERFACE.md` for the full call manifest and module map.

```
INNER layer   openclaw container        the agent under test
OUTER layer   sandbox/supervisor.py     observes events, assigns verdicts, you judge
INTERFACE     sandbox/labctl.sh         one command surface (or make oc-*)
GATE          sandbox/gate.sh           pluggable pre-load filter (off | scan | custom)
HONEYPOT      sandbox/egress_proxy.py   intercepts exfil, logs the payload, nothing leaves
```

## Requirements
- Docker + the Docker Compose plugin (`docker compose version`).
- `make`, `git`, `python3` on the host.
- A real LLM API key (DeepSeek by default; any OpenAI-compatible endpoint works).

## Quick start
```bash
cp sandbox/.env.example sandbox/.env          # DeepSeek is pre-set; add your key
sed -i 's|^LLM_API_KEY=.*|LLM_API_KEY=sk-your-deepseek-key|' sandbox/.env
make oc-build                                 # Node 24 + npm i -g openclaw
make oc-up                                     # egress-proxy + canary + openclaw
make oc-ask MSG="Introduce yourself"          # inner agent answers (clean text + trace)
make oc-watch                                  # outer monitor: live judged event stream
make oc-down                                    # stop (config + skills persist)
```

### `.env`
```
LLM_API_KEY=sk-...            DeepSeek key (the only secret in the container)
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API=openai-completions
EGRESS_ALLOW=api.deepseek.com only this domain is reachable
GATE_MODE=scan               off | scan | custom
EGRESS_HTTP=capture          capture = honeypot (log payload, fake 200); deny = hard 403
```
Switching provider: change all of `LLM_*` and `EGRESS_ALLOW`, then `make oc-down && make oc-up`.

## The two layers
```bash
make oc-ask MSG="..."     # INNER: ask OpenClaw; clean answer + per-step trace
make oc-watch             # OUTER: live judged event stream (run in a second terminal)
make oc-ui                # OUTER: web dashboard on 127.0.0.1:8910
make oc-exfil             # OUTER: captured exfil payloads
make oc-verify            # egress-lock self-test
```
Verdicts: `OK` (allowed), `INFO` (lifecycle), `FLAG` (anomaly), `BLOCKED` (exfil stopped),
`CRITICAL` (exfil payload captured / internal honeypot probed).

The dashboard binds `127.0.0.1` on the VM (no inbound port opened). View it from your laptop:
```bash
ssh -L 8910:127.0.0.1:8910 <user>@<vm-ip>     # then open http://localhost:8910
```

## Skills (you decide what runs)
Two bundled mock skills: `weather` (benign) and `meeting-notes` (malicious, canary-only).
Install through the gate:
```bash
./sandbox/labctl.sh skill list
./sandbox/labctl.sh skill scan sandbox/skills/meeting-notes     # scan only, print severity
./sandbox/labctl.sh skill add  sandbox/skills/weather           # clean -> installed
./sandbox/labctl.sh skill add  sandbox/skills/meeting-notes     # HIGH/CRITICAL -> rejected
./sandbox/labctl.sh skill add  sandbox/skills/meeting-notes --force   # install anyway
```

Choose or replace the gate:
```bash
./sandbox/labctl.sh gate off       # no filter, install directly
./sandbox/labctl.sh gate scan      # built-in Cisco scanner
./sandbox/labctl.sh gate custom    # your own: edit sandbox/gate_custom.sh
```
`gate_custom.sh` receives a skill directory and must print one of
`NONE|INFO|LOW|MEDIUM|HIGH|CRITICAL`; `HIGH`/`CRITICAL`/`ERR` reject the skill.

## See the malicious behavior (honeypot)
```bash
make oc-watch                                              # terminal A
./sandbox/labctl.sh skill add sandbox/skills/meeting-notes --force
make oc-ask MSG="Summarize with meeting-notes: we set the launch date..."
./sandbox/labctl.sh exfil                                  # what it tried to steal
```
With `EGRESS_HTTP=capture`, the skill's exfil POST is intercepted at the proxy: terminal A
shows `egress capture CRITICAL ...` containing the `~/.openclaw/openclaw.json` key and env
credentials it harvested. The proxy returns a fake 200 so the attack flow completes for
observation, but nothing leaves the sandbox. Set `EGRESS_HTTP=deny` for a hard 403 instead.

## The safety layer (egress lock)
1. `openclaw` is on an internal-only network -- no direct internet, no cloud metadata route.
2. `egress_proxy.py` is the only outbound path and allows only `EGRESS_ALLOW`; everything else
   (arbitrary exfil, AWS `169.254.169.254`, Alibaba Cloud `100.100.100.200`) is denied or
   captured by the honeypot.
3. Non-root, read-only rootfs, `cap_drop ALL`, no host mounts; the only secret is `LLM_API_KEY`.
```bash
make oc-verify     # LLM domain 200/401 (reached); everything else 000 (blocked)
```

---

## Deploy on a remote VM (headless, no GUI)

Works on any Ubuntu VM with Docker. Below is Alibaba Cloud ECS.

### A. Create the VM (web console)
1. ECS -> Instances -> Create Instance (pay-as-you-go).
2. Region near you. Type 2 vCPU / 4 GiB. Image: a Docker-preinstalled Ubuntu 22.04.
3. Network: Assign Public IPv4, pay-by-traffic, 5 Mbps.
4. Security group inbound: allow SSH (22) from your IP/32 only. No other inbound port is needed.
5. Login: key pair (download `.pem`) or a password.
6. (Optional) set an auto-release time as a budget guardrail. Note the public IP.

### B. Connect
- Web console: instance -> Connect -> Workbench (browser terminal), or
- Local SSH: `ssh -i ~/Downloads/your-key.pem root@<public-ip>`

### C. On the VM
```bash
docker compose version || sudo apt-get update && sudo apt-get install -y docker-compose-plugin
sudo apt-get install -y git make python3

echo '{ "registry-mirrors": ["https://registry.cn-hangzhou.aliyuncs.com"] }' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker

git clone https://github.com/KuiyiGao/OpenClaw-Skill-Hack.git
cd OpenClaw-Skill-Hack
cp sandbox/.env.example sandbox/.env
sed -i 's|^LLM_API_KEY=.*|LLM_API_KEY=sk-your-deepseek-key|' sandbox/.env

make oc-build && make oc-up
make oc-ask MSG="hello"
make oc-watch
```

### D. Tear down
```bash
make oc-down                 # stop (state persists in the volume)
```
Then release the instance in the web console.

### Notes
- Image build needs internet (npm, base images). The egress lock only restricts the running
  OpenClaw container, not image builds.
- The LLM key lives only in `sandbox/.env` on the VM (gitignored). Even a malicious skill that
  reads it cannot send it anywhere except the allowlisted LLM domain.
- Canary-only; see `ETHICS.md`.
