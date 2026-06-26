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

**Node bootstrap (host mode, no Docker):** the package ships a small
`--require` helper that installs an undici `ProxyAgent` as the global
dispatcher, so OpenClaw's native `fetch()` actually transits the proxy.
Verified against `openclaw@2026.6.10`: `clawhub.ai` CONNECT events
appear in `events.jsonl`.

```bash
npm install -g undici                        # one-time, so the script resolves it
firewall start
export FIREWALL_PROXY=http://127.0.0.1:8080
NODE_OPTIONS="--require $(firewall integrations openclaw-bootstrap)" \
  openclaw skills search hello
```

`HTTP_PROXY`/`HTTPS_PROXY` env vars still help — they catch any
**subprocess** a skill spawns (`curl`, `pip`, `npm`, etc.), even though
OpenClaw's own egress slips them.

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

Walks the standard project + user dirs and parses every `SKILL.md` it
finds. No framework-specific code in the firewall.

```
project (walked from cwd up to /)        user ($HOME)
─────────────────────────────────        ────────────────────────
.openclaw/skills                         ~/.openclaw/skills
.openclaw/workspace/skills               ~/.openclaw/workspace/skills
.claude/skills                           ~/.claude/skills
.claude-plugin/skills                    ~/.agents/skills
.agents/skills                           ~/.config/opencode/skills
.cursor/skills · .codex/skills
.gemini/skills · .opencode/skills
skills/        (bare project)
```

## Verdict ladder

```
       evidence (tool calls, egress, answer)
                       │
                       ▼
        ┌──────────────────────────────┐
        │ host classified hostile?     │── yes ─▶ MALICIOUS  (block)
        │ cross-plane taint?           │             score 85
        │ injection compliance?        │
        └──────────────┬───────────────┘
                       │ no
                       ▼
        ┌──────────────────────────────┐
        │ any divergence from intent?  │── yes ─▶ SUSPICIOUS (defer / tighten egress)
        └──────────────┬───────────────┘             score 40+
                       │ no
                       ▼
                    BENIGN (pass)
```

The 5 invariants the verdict ladder enforces are in
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

The judge prompt is opt-in. The runtime is fully deterministic by default;
set `judge_prompt_path` only if you want an LLM tie-breaker on top.

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
(46 driver refusals, 19 dependency-locked); the runtime layer's job is
to back-stop the static layer, not replace it.

The dataset is not shipped with the public package. Two example skills
are: `firewall/examples/skills/weather-safe` and
`firewall/examples/skills/weather-malicious-canary`.

## Layout

```
firewall/
  cli.py            firewall start | panel | config | scan | watch | hook | skills
  config.py         all patterns + TOML loader
  runtime/
    firewall.py     L2 IAR verifier  (~250 lines, policy-free)
    egress_proxy.py L1 proxy: allow / deny / capture
    canary.py       L1 honeypot tripwire
    supervisor.py   log lines → events
    events.py       JSONL emitter the panel tails
  gate/
    static_scanner.py   L0 static scan
  skills/
    discover.py     walks .openclaw/.claude/.cursor/… skill dirs
  panel/
    tui.py          Textual live panel
  docker/           minimal compose stack
  examples/         weather-safe + weather-malicious-canary
tests/unit/         17 tests, one per invariant + regressions
experiment_minimal/ small CSV runner + browser dashboard
docs/code.tex       source for code.pdf (companion document)
```

## License

MIT — see [LICENSE](LICENSE).
