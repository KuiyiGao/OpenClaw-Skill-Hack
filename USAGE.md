# Usage

Run real OpenClaw in an isolated sandbox against a real LLM, with egress locked down so the
agent (and any skill it loads) cannot reach your credentials or cloud metadata.

> The disposable VM is only the *host*. You configure once, install many skills, restart freely
> (state persists in a named volume). Container isolation + the egress lock are the security
> boundary; a cloud VM is just extra defense-in-depth. You can also run it locally with Docker.

## Requirements
- Docker + the Docker Compose plugin (`docker compose version`).
- `make`, `git`, `python3` on the host.
- A real LLM API key (DeepSeek by default; any OpenAI-compatible endpoint works).

## Quick start
```bash
cp sandbox/.env.example sandbox/.env     # set LLM_API_KEY / LLM_MODEL / LLM_BASE_URL / EGRESS_ALLOW
make oc-build                            # build the OpenClaw image (Node 24 + npm i -g openclaw)
make oc-up                               # start egress-proxy + canary + openclaw (stays running)
make oc-ask MSG="Introduce yourself"     # OpenClaw answers using the real model
make oc-monitor                          # watch reactions / canary hits / blocked egress
make oc-down                             # stop (config + installed skills persist)
```

### `.env`
```
LLM_API_KEY=sk-...                       # your real key (the only secret in the container)
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API=openai-completions               # openai-completions | openai-responses | anthropic-messages
EGRESS_ALLOW=api.deepseek.com            # only this domain is reachable; change with your provider
```
Switching provider: change all of `LLM_*` **and** `EGRESS_ALLOW` (allow the new domain), then `make oc-up`.

## The safety layer (egress lock)
Three independent guards keep credentials safe even if a malicious skill is loaded:
1. The `openclaw` container is on an **internal-only** network -- no direct internet, no cloud metadata route.
2. `egress_proxy.py` is the only outbound path and **allows only `EGRESS_ALLOW`**; everything else
   (arbitrary exfil, AWS `169.254.169.254`, Alibaba Cloud `100.100.100.200`) is denied.
3. Non-root, read-only rootfs, `cap_drop ALL`, no host mounts; the only secret is `LLM_API_KEY`.

Verify it:
```bash
ex(){ docker compose -f sandbox/docker-compose.yml --env-file sandbox/.env exec -T openclaw bash -lc "$1"; }
ex 'curl -s -o /dev/null -w "LLM(allow): %{http_code}\n"   --max-time 10 https://api.deepseek.com/v1/models'
ex 'curl -s -o /dev/null -w "exfil(deny): %{http_code}\n"  --max-time 8  https://example.com'
ex 'curl -s -o /dev/null -w "metadata(deny): %{http_code}\n" --max-time 6 http://100.100.100.200/'
```
Expected: the LLM domain connects (200 with a real key); everything else returns `000` (denied).

## Skills (you decide what runs)
Two bundled mock skills live in `sandbox/skills/` (`weather` = benign, `meeting-notes` = malicious,
canary-only). Add skills only through the scan-then-load gate:
```bash
./sandbox/skillctl.sh list                          # installed skills
./sandbox/skillctl.sh scan sandbox/skills/meeting-notes   # scan only, print severity
./sandbox/skillctl.sh add  sandbox/skills/weather   # clean -> installed; HIGH/CRITICAL -> rejected
./sandbox/skillctl.sh add  <your-skill-dir> --force # install anyway (your explicit approval)
```
The Cisco scanner is optional; if its image is missing the gate self-builds it, and if it can't, it
returns `SKIP` without blocking. To wire your own scanner, edit `sandbox/cisco_scan.sh`.

---

## Deploy on a remote VM (headless, no GUI)

Works the same on any Ubuntu VM with Docker. Below is Alibaba Cloud ECS (web console + CLI).

### A. Create the VM (web console)
1. Console -> **Elastic Compute Service (ECS) -> Instances -> Create Instance** (pay-as-you-go).
2. Region: pick one near you. Instance type: **2 vCPU / 4 GiB**. Image: **Ubuntu 22.04 64-bit**.
3. Network: tick **Assign Public IPv4**, pay-by-traffic, 5 Mbps.
4. Security group inbound: allow **SSH (22) only from your own IP/32** (remove any `0.0.0.0/0` rule for 22).
5. Login: **key pair** (download the `.pem`) or a custom password.
6. (Optional) set an **auto-release time** as a budget guardrail. Create, then note the public IP.

### B. Connect (no GUI needed)
- Web console: instance -> **Connect -> Workbench** (browser terminal, user `root`), or
- Local SSH: `ssh -i ~/Downloads/your-key.pem root@<public-ip>`

### C. On the VM
```bash
# 1) tools
sudo apt-get update && sudo apt-get install -y git make python3
docker compose version || sudo apt-get install -y docker-compose-plugin

# 2) (China regions) Docker registry mirror so image pulls are fast
echo '{ "registry-mirrors": ["https://registry.cn-hangzhou.aliyuncs.com"] }' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker

# 3) get the code (git clone <your repo>, or rsync/scp from your laptop), then:
cd OpenClaw-Skill-Hack
cp sandbox/.env.example sandbox/.env && nano sandbox/.env    # fill LLM_API_KEY etc.

# 4) run
make oc-build && make oc-up
make oc-ask MSG="hello"
make oc-monitor
```

### D. Tear down
```bash
make oc-down                 # stop containers (state persists in the volume)
```
Then in the web console: **release the instance** (pay-as-you-go stops billing on release), and
clean up the EIP / security group / key pair if you created them just for this.

### Notes
- Image build needs internet (npm, base images). That is normal -- the egress lock only restricts
  the **running** OpenClaw container, not image builds.
- The LLM key lives only in `sandbox/.env` on the VM (gitignored). The egress lock means even if a
  malicious skill reads it, it cannot send it anywhere except the allowlisted LLM domain.
- Canary-only; see [ETHICS.md](ETHICS.md).
