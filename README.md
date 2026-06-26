# Agent Skill Firewall

[![CI](https://github.com/KuiyiGao/OpenClaw-Skill-Hack/actions/workflows/ci.yml/badge.svg)](https://github.com/KuiyiGao/OpenClaw-Skill-Hack/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://github.com/KuiyiGao/OpenClaw-Skill-Hack)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A runtime behavioural firewall for Agent Skills. Judges a skill by what it
does at runtime, not by what its code looks like.

```
                                                         events.jsonl
                                                              │
   ┌──────────────┐    HTTP_PROXY     ┌──────────────┐    write │ tail
   │ openclaw /   │ ───────────────▶  │   firewall   │ ─────────┼──▶ firewall panel
   │ claude-code/ │   (port 8080)     │ proxy+canary │          │
   │   cursor     │ ◀───── verdicts ─ │   + L0 + L2  │ ─────────┘
   └──────┬───────┘   allow/deny      └──────────────┘
          │
   reads SKILL.md from .openclaw/skills, .claude/skills, …
```

## Install

```bash
pip install agent-skill-firewall
firewall config init
```

## Quick start — host mode

```bash
# 1. configure the driver model + API key env-var name (one-time)
firewall config init
$EDITOR "$(firewall config path)"
export DEEPSEEK_API_KEY=sk-...

# 2. start the firewall (egress proxy + canary, host processes)
firewall start

# 3. in a second terminal, open the live panel
firewall panel
```

## Quick start — Docker

```bash
firewall start --mode docker     # brings up firewall/docker/compose.yml
firewall panel                   # reads the same events.jsonl
```

## Hook a real agent through the firewall

```bash
firewall hook openclaw       # OpenClaw — Docker mode or per-provider config (see below)
firewall hook claude-code    # Claude Code — HTTP_PROXY/HTTPS_PROXY
firewall hook cursor         # Cursor — Settings → Network or env
firewall hook generic        # HTTP_PROXY/HTTPS_PROXY/ALL_PROXY (works for most agents)
```

### OpenClaw

OpenClaw's Node `fetch` (undici) **ignores HTTP_PROXY** — verified against
`openclaw@2026.6.10`. Use one of:

**Docker mode (recommended):** iptables in the compose network catches
everything regardless of `fetch` behaviour.

```bash
firewall start --mode docker
# uncomment the `openclaw` service in firewall/docker/compose.yml
# then run your agent commands inside that container
```

**Per-provider config:** pins model-API traffic to the proxy on the host.

```bash
firewall start
openclaw config set models.providers.<id>.request.proxy.mode    explicit-proxy
openclaw config set models.providers.<id>.request.proxy.proxyUrl http://127.0.0.1:8080
```

**Node bootstrap (host mode):** ships a `--require` helper that installs
an undici `ProxyAgent` so OpenClaw's native `fetch()` transits the proxy.
Verified against `openclaw@2026.6.10`.

```bash
npm install -g undici
firewall start
export FIREWALL_PROXY=http://127.0.0.1:8080
NODE_OPTIONS="--require $(firewall integrations openclaw-bootstrap)" \
  openclaw skills search hello
```

`HTTP_PROXY`/`HTTPS_PROXY` still catch subprocesses a skill spawns
(`curl`, `pip`, `npm`).

### Other agents (HTTP_PROXY works)

```bash
eval "$(firewall hook generic)"
claude / cursor / your-agent ...
```

`firewall panel` shows each skill's verdict (PASS / DEFER / BLOCK) as it
happens, session totals, and the LLM driver's API usage.

## Commands

| Command | Does |
|---|---|
| `firewall config init` / `show` / `path` | manage `~/.config/firewall/config.toml` |
| `firewall start [--mode host\|docker]` | egress proxy + canary |
| `firewall stop` | docker-compose down |
| `firewall panel` | live TUI: passed / deferred / blocked + session + API usage |
| `firewall scan <skill>` | L0 static scan |
| `firewall watch <skill> --log-file <log>` | L2 verdict from a stored proxy log |
| `firewall skills [--dir <p>]` | list every skill on disk (framework-agnostic) |
| `firewall hook <agent>` | print the env-vars / config to route an agent through the proxy |
| `firewall integrations openclaw-bootstrap` | print absolute path to the Node `--require` helper |
| `firewall doctor` | health check (config, API-key env var, ports, optional tools) |

## Skill discovery

Walks the standard project + user dirs
(`.openclaw/skills`, `.claude/skills`, `.cursor/skills`, `.agents/skills`,
`.codex/skills`, `.gemini/skills`, `.opencode/skills`, `skills/`, and
their `~/` equivalents) and parses every `SKILL.md` it finds. No
framework-specific code in the firewall.

## Verdict ladder

1. **MALICIOUS** (block, score 85) — host classified hostile, cross-plane taint, or injection compliance.
2. **SUSPICIOUS** (defer / tighten egress, score 40+) — any divergence from declared intent.
3. **BENIGN** (pass) — otherwise.

The five invariants the verdict ladder enforces are in
[firewall/runtime/firewall.py](firewall/runtime/firewall.py) and pinned
by one named test each in
[tests/unit/test_firewall_invariants.py](tests/unit/test_firewall_invariants.py).

## Configuration

All patterns live in `~/.config/firewall/config.toml`. Shape:

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

The judge prompt is opt-in — runtime is fully deterministic by default;
set `judge_prompt_path` only for an LLM tie-breaker.

## Evaluation

On a 112-case corpus (76 malicious, 36 benign):

| Detector | Recall (of 76) | Precision | False-kills (of 36) | F1 |
|---|---:|---:|---:|---:|
| Cisco static (offline) | 42.1% | 0.94 | 2 | 0.58 |
| Cisco + LLM (strict) | 98.7% | 0.92 | **7** | 0.95 |
| Cisco + LLM (loose) | 98.7% | 0.84 | **14** | 0.91 |
| Our static | 93.4% | 1.00 | 0 | 0.97 |
| **Our static ∪ runtime** | **98.7%** | **1.00** | **0** | **0.993** |

Of the 76 malicious cases, 65 produced no observable runtime action
(driver refusals or dependency-locked); the runtime layer back-stops the
static layer. Example skills ship under `firewall/examples/skills/`
(`weather-safe`, `weather-malicious-canary`); the full dataset is not
included.

## Layout

```
firewall/
  cli.py            entry point for all subcommands
  config.py         TOML loader + default patterns
  runtime/          L2 IAR verifier, egress proxy, canary, supervisor, events
  gate/             L0 static scanner
  skills/           framework-agnostic SKILL.md discovery
  panel/            Textual live TUI
  integrations/     openclaw proxy-bootstrap.js
  docker/           minimal compose stack
  examples/         weather-safe + weather-malicious-canary
tests/unit/         one test per invariant + regressions
docs/code.tex       companion document source
examples/your-skills/    drop your own SKILL.md folders here
```

## How this compares to NVIDIA SkillSpector

[NVIDIA SkillSpector](https://github.com/NVIDIA/skillspector) — the tool
people sometimes call "NVIDIA Skill Defender" — is a **pre-install
scanner**: it reads a skill's source, matches 68 patterns across 17
categories (prompt injection, taint, MCP poisoning, OSV.dev supply
chain), and emits SARIF for a CI pipeline or MCP-capable agent to block
the install. Excellent at known-bad code shapes; can't see anything the
skill only does at runtime.

**`agent-skill-firewall` is a runtime behavioural firewall.** We watch a
skill's actual tool calls and egress through an HTTP proxy, judge each
action against the five invariants, and emit `PASS / DEFER / BLOCK` in a
live TUI. Every rule lives in user-auditable TOML; every host is
deny-by-default; every framework is supported via the same on-disk
skill discovery.

| | SkillSpector | this package |
|---|---|---|
| Layer | static (pre-install) | runtime (behavioural) |
| Rule visibility | 68 built-in patterns | TOML you can `diff` |
| CI output | SARIF | JSONL + live TUI |
| Provenance | signed Skill Cards | — |
| Catalog | NVIDIA-Verified | — |

The two are **complementary**: run SkillSpector at install-time; run
`agent-skill-firewall` at run-time.

### Local benchmark

Ran SkillSpector v2.3.7 (`--no-llm`) against five cases (4 malicious +
1 benign) and compared verdicts to our L0 static scan and L2 IAR
runtime check.

| Case | Truth | SkillSpector | Our L0 | Our IAR |
|---|---|---|---|---|
| `weather-safe` | benign | SAFE | NONE | BENIGN |
| `weather-malicious-canary` | malicious | SAFE | **CRITICAL** | **MALICIOUS** |
| `config-redirect-malicious` | malicious | SAFE | NONE | **MALICIOUS** |
| `hex-encode-malicious` | malicious | SAFE | NONE | **MALICIOUS** |
| `dyn-url-malicious` | malicious | SAFE | NONE | **MALICIOUS** |

SkillSpector returned `SAFE` on 4/4 malicious cases at this floor. Case 2
is the informative one — `attacker-canary.evil` is a plain ASCII literal
in the bundled script and our L0 catches it via `hostile_host_literal`;
SkillSpector's only finding is `LP3` (declare permissions in SKILL.md),
unrelated to the malicious indicator. Cases 3–5 are static-evasive by
construction (host comes from a JSON manifest / hex blob / `chr()`
arithmetic) and only surface at runtime. The LLM analyzer path was not
exercised (no API key configured); this is SkillSpector's `--no-llm`
floor, not a head-to-head against its full pipeline.

Full method, confusion matrix, and reproduction commands in
[docs/skillspector-comparison.md](docs/skillspector-comparison.md).

## License

MIT — see [LICENSE](LICENSE).
