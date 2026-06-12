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

## Model provider (DeepSeek / K2 switch)
DeepSeek is the default. **K2 (Kimi K2 via [ifm.ai](https://ifm.ai/docs))** is a second, separate
provider profile with a reserved key slot. Each profile carries its own key, model, base URL, and
egress domain; switching flips the active `LLM_*` **and** the egress allowlist (least privilege --
only the active provider's domain is reachable).
```bash
# fill the K2 slot in sandbox/.env from https://ifm.ai/docs (key, exact model id, base url)
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

## Skills (you decide what runs)
Two bundled mock skills live in `sandbox/skills/`: `weather` (benign) and `meeting-notes`
(malicious, canary-only -- it tries to steal the LLM key and exfiltrate it). Install via the gate:
```bash
./sandbox/labctl.sh skill scan sandbox/skills/meeting-notes   # scan only, print severity
./sandbox/labctl.sh skill add  sandbox/skills/weather         # clean -> installed
./sandbox/labctl.sh skill add  sandbox/skills/meeting-notes   # HIGH/CRITICAL -> rejected
./sandbox/labctl.sh gate off|scan|custom                      # choose the pre-load filter
```

Canary-only research use; see [ETHICS.md](ETHICS.md).
