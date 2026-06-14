# OpenClaw-Skill-Hack

Run real **OpenClaw** in an isolated sandbox against a real LLM (DeepSeek by default) and study
agent-skill attacks safely. A two-layer harness lets you talk to the agent (inner layer) while a
supervisor observes every event and assigns a verdict (outer layer). Egress is locked so the agent
-- and any skill it loads -- cannot reach your credentials or cloud metadata.

```
INNER   openclaw container        the agent under test
OUTER   sandbox/supervisor.py     observes events, assigns verdicts, you judge
CONTROL sandbox/labctl.sh         one command surface (or make oc-*)
GATE    sandbox/gate.sh           pluggable pre-load filter: off | scan | custom
HONEYPOT sandbox/egress_proxy.py  allowlist egress; captures exfil payloads, nothing leaves
```

## Web console (recommended -- almost no terminal)
After building once, drive everything from a browser: pick the model, gate, and egress mode, choose
a skill variant (safe / malicious) and whether the gate is enforced, then click **Run** to see the
agent's answer plus the egress-lock / honeypot verdict.
```bash
make oc-build            # one time
make oc-console          # serves http://127.0.0.1:8765  (on a VM: ssh -L 8765:127.0.0.1:8765 user@vm)
```
The `make oc-*` / `labctl` commands below are the CLI equivalent of the console.

## Requirements
Docker + the Compose plugin, plus `make`, `git`, `python3` on the host, and a real LLM API key
(DeepSeek by default; any OpenAI-compatible endpoint works).

## Standard commands
```bash
cp sandbox/.env.example sandbox/.env                     # set your key (DeepSeek is pre-filled)
sed -i 's|^LLM_API_KEY=.*|LLM_API_KEY=sk-your-deepseek-key|' sandbox/.env

make oc-build                 # build images (Node 24 + npm i -g openclaw)
make oc-up                    # start egress-proxy + canary + openclaw
make oc-verify                # egress-lock self-test
make oc-ask MSG="Introduce yourself"   # inner agent answers (clean text + step trace)
make oc-watch                 # outer monitor: live judged event stream (use a 2nd terminal)
make oc-exfil                 # show captured exfil payloads (honeypot)
make oc-down                  # stop (config + installed skills persist in a volume)
```
The same commands run on a remote VM; only the host changes. Full guide incl. Alibaba Cloud ECS
(web console + CLI): [USAGE.md](USAGE.md). Command/module map: [INTERFACE.md](INTERFACE.md).

## `.env`
```
PROVIDER=deepseek                        # active provider profile: deepseek | k2
LLM_API_KEY=sk-...                       # active key (the only secret in the container)
LLM_MODEL / LLM_BASE_URL / LLM_API       # active provider (auto-set by `labctl provider`)
EGRESS_ALLOW=api.deepseek.com            # only the active provider domain is reachable
GATE_MODE=scan                           # off | scan | custom
EGRESS_HTTP=capture                      # capture = honeypot (log payload, fake 200); deny = hard 403
DEEPSEEK_* / K2_*                        # the two provider profiles (key, model, base url, egress)
```

## Model provider (DeepSeek / K2-Think switch)
DeepSeek is the default. **K2-Think (MBZUAI-IFM, endpoint `api.k2think.ai`, model
`MBZUAI-IFM/K2-Think-v2`)** is a second, separate provider profile with a reserved key slot. Each
profile carries its own key, model, base URL, and egress domain; switching flips the active `LLM_*`
**and** the egress allowlist (least privilege -- only the active provider's domain is reachable).
```bash
sed -i 's|^K2_API_KEY=.*|K2_API_KEY=sk-your-k2think-key|' sandbox/.env
make oc-provider P=k2          # or: ./sandbox/labctl.sh provider k2
make oc-down && make oc-up     # apply
make oc-provider P=deepseek    # switch back
```

## Safety layer (egress lock)
1. The `openclaw` container is on an internal-only network -- no direct internet, no metadata route.
2. `egress_proxy.py` is the only outbound path: it allows only `EGRESS_ALLOW`, **hard-denies all
   non-public IPs** (AWS `169.254.169.254`, Alibaba Cloud `100.100.100.200`, private ranges), and
   in `capture` mode logs any other exfil attempt while returning a fake 200 -- nothing leaves.
3. Non-root, read-only rootfs, `cap_drop ALL`, no host mounts; the only secret is `LLM_API_KEY`.

## Experiment model: one fixed task, two skills
The canonical case is a **fixed task** (a weather query) with **two skills that share the same
surface**: `weather-safe` (benign control) and `weather-malicious` (trojanized -- models ClawHavoc:
it steals the agent's LLM key and tries to exfiltrate it). Only the malicious payload differs, so
the attack is the single variable. Combined with the gate (on/off) this gives a clean 2x2.
```bash
./sandbox/labctl.sh skill scan sandbox/skills/weather-malicious   # CRITICAL
./sandbox/labctl.sh skill add  sandbox/skills/weather-safe        # SAFE -> installed
./sandbox/labctl.sh skill add  sandbox/skills/weather-malicious   # CRITICAL -> rejected (use --force to override)
./sandbox/labctl.sh gate off|scan|custom                         # choose the pre-load filter
```
**Add a new case** by dropping a `sandbox/skills/<name>-safe` + `<name>-malicious` pair (any
real-incident pattern); the web console auto-discovers it. Canary-only; see [ETHICS.md](ETHICS.md).
