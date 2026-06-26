"""Declarative registry of the agent frameworks the firewall adapts to.

Adapting a new agent means answering two questions, and nothing else:

  1. Where does it keep its SKILL.md folders?      -> project_dirs / home_dirs
  2. How does its traffic reach the network?       -> egress + hook_lines

Both `firewall/skills/discover.py` (what to scan) and `firewall hook`
(how to route) read from this one file, so a new framework is a single
`AgentProfile` entry — see `hermes` below for a ~12-line example.

The `egress` field is the important abstraction. It classifies *how* an
agent's HTTP actually leaves the process, which is the only thing that
decides whether a plain `HTTP_PROXY` is enough:

  "env"          The runtime honours HTTP_PROXY / HTTPS_PROXY on its own.
                 True for Python clients (requests, httpx with trust_env,
                 urllib) and most CLI tools. Hook = export the env vars.
                 Agents: hermes (Python), claude-code, generic.

  "node-undici"  Node's global fetch (undici) IGNORES HTTP_PROXY. The env
                 vars only catch subprocesses (curl/pip/npm), not the
                 agent's own model calls. Needs an undici ProxyAgent
                 injected via `--require`, or Docker-network interception.
                 Agents: openclaw.

  "app-config"   The app has its own proxy setting rather than reading the
                 environment. Hook = print the config command / UI path.
                 Agents: cursor (Settings -> Network).

Some agents are hybrids (OpenClaw is node-undici *and* has per-provider
config); `egress` names the dominant/interesting case and `hook_lines`
prints whatever the user actually needs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class AgentProfile:
    key: str                              # canonical name, e.g. "hermes"
    display: str                          # human label, e.g. "Hermes Agent"
    egress: str                           # "env" | "node-undici" | "app-config"
    hook_lines: Callable[[str], list[str]]  # proxy_url -> shell/how-to lines
    aliases: tuple[str, ...] = ()         # extra names that resolve here
    project_dirs: tuple[str, ...] = ()    # skill dirs discovered per project (rel to cwd chain)
    home_dirs: tuple[str, ...] = ()       # skill dirs under $HOME
    runtime: str = ""                     # short note: "Python", "Node", ...


# --------------------------------------------------------------------------- #
# Per-agent hook builders. Each takes the proxy URL and returns the lines the
# user copy-pastes. Kept as functions so the port/host are substituted live.
# --------------------------------------------------------------------------- #

def _hook_env(proxy: str) -> list[str]:
    return [
        "# HTTP-aware agent: export the proxy, then start the agent here.",
        f"export HTTP_PROXY={proxy}",
        f"export HTTPS_PROXY={proxy}",
        f"export ALL_PROXY={proxy}",
    ]


def _hook_hermes(proxy: str) -> list[str]:
    return [
        f"# Hook Hermes Agent through the firewall (proxy at {proxy}).",
        "#",
        "# Hermes is Python (httpx / requests), which honours these env vars",
        "# out of the box — no bootstrap needed, unlike OpenClaw's Node fetch.",
        f"export HTTP_PROXY={proxy}",
        f"export HTTPS_PROXY={proxy}",
        f"export ALL_PROXY={proxy}",
        "#",
        "# httpx only reads the environment when trust_env is on (the default);",
        "# if you set it False in a custom endpoint, pass proxies= explicitly.",
        "#",
        "# Then run Hermes normally in the SAME shell:",
        "#   hermes                       # interactive",
        '#   hermes run "summarise ./notes"',
        "#",
        "# Skills are read from ~/.hermes/skills (and skills.external_dirs in",
        "# ~/.hermes/config.yaml). Scan them first with:  firewall skills",
    ]


def _hook_openclaw(proxy: str) -> list[str]:
    return [
        f"# Hook OpenClaw through the firewall (proxy at {proxy}).",
        "#",
        "# OpenClaw uses Node's native fetch (undici), which IGNORES",
        "# HTTP_PROXY. Verified against openclaw 2026.6.10. Use one of:",
        "#",
        "# Option A - Node bootstrap (host mode): inject an undici ProxyAgent.",
        "  npm install -g undici",
        f"  export FIREWALL_PROXY={proxy}",
        '  export NODE_OPTIONS="--require $(firewall integrations openclaw-bootstrap)"',
        "  #   then run openclaw normally, e.g. openclaw skills search hello",
        "#",
        "# Option B - Docker mode: the compose network catches everything.",
        "  cd firewall/docker && docker compose --profile agent up",
        "#",
        "# Option C - pin one model provider through the proxy. The proxy is a",
        "# single object (set it whole, not field-by-field), the key is 'url',",
        "# and <id> must be a real provider from `openclaw config get models.providers`:",
        f"  openclaw config set 'models.providers.<id>.request.proxy' '{{\"mode\":\"explicit-proxy\",\"url\":\"{proxy}\"}}'",
        "  #   then restart the gateway to apply.",
        "#",
        "# HTTP_PROXY still catches skill subprocesses (curl, pip, npm):",
        f"export HTTP_PROXY={proxy}; export HTTPS_PROXY={proxy}; export ALL_PROXY={proxy}",
    ]


def _hook_claude_code(proxy: str) -> list[str]:
    return [
        "# Hook Claude Code through the firewall.",
        f"export HTTP_PROXY={proxy}; export HTTPS_PROXY={proxy}",
        "# then run:  claude",
    ]


def _hook_cursor(proxy: str) -> list[str]:
    return [
        "# Hook Cursor: Settings -> Network -> HTTP/HTTPS Proxy",
        f"#   HTTP Proxy:  {proxy}",
        f"#   HTTPS Proxy: {proxy}",
        "# or via env before launch:",
        f"export HTTP_PROXY={proxy}; export HTTPS_PROXY={proxy}",
    ]


# --------------------------------------------------------------------------- #
# The registry. Order matters only for display.
# --------------------------------------------------------------------------- #

_PROFILES: tuple[AgentProfile, ...] = (
    AgentProfile(
        key="openclaw", display="OpenClaw", egress="node-undici", runtime="Node",
        aliases=("open-claw",),
        project_dirs=(".openclaw/skills", ".openclaw/workspace/skills"),
        home_dirs=(".openclaw/skills", ".openclaw/workspace/skills"),
        hook_lines=_hook_openclaw,
    ),
    AgentProfile(
        key="hermes", display="Hermes Agent", egress="env", runtime="Python",
        aliases=("hermes-agent", "nous-hermes"),
        project_dirs=(".hermes/skills",),
        home_dirs=(".hermes/skills",),
        hook_lines=_hook_hermes,
    ),
    AgentProfile(
        key="claude-code", display="Claude Code", egress="env", runtime="Node/native",
        aliases=("claude", "claudecode"),
        project_dirs=(".claude/skills", ".claude-plugin/skills"),
        home_dirs=(".claude/skills",),
        hook_lines=_hook_claude_code,
    ),
    AgentProfile(
        key="cursor", display="Cursor", egress="app-config", runtime="Electron",
        project_dirs=(".cursor/skills",),
        hook_lines=_hook_cursor,
    ),
    AgentProfile(
        key="codex", display="Codex CLI", egress="env", runtime="Node",
        project_dirs=(".codex/skills",),
        hook_lines=_hook_env,
    ),
    AgentProfile(
        key="gemini", display="Gemini CLI", egress="env", runtime="Node",
        project_dirs=(".gemini/skills",),
        hook_lines=_hook_env,
    ),
    AgentProfile(
        key="opencode", display="OpenCode", egress="env", runtime="Go",
        project_dirs=(".opencode/skills",),
        home_dirs=(".config/opencode/skills",),
        hook_lines=_hook_env,
    ),
    AgentProfile(
        key="agents", display="Agents CLI", egress="env", runtime="—",
        project_dirs=(".agents/skills",),
        home_dirs=(".agents/skills",),
        hook_lines=_hook_env,
    ),
    AgentProfile(
        key="generic", display="Any HTTP-aware agent", egress="env", runtime="—",
        hook_lines=_hook_env,
    ),
)

REGISTRY: dict[str, AgentProfile] = {}
for _p in _PROFILES:
    REGISTRY[_p.key] = _p
    for _a in _p.aliases:
        REGISTRY[_a] = _p


def resolve(agent: str) -> AgentProfile:
    """Look up a profile by key or alias; fall back to the generic profile."""
    return REGISTRY.get(agent.lower().strip(), REGISTRY["generic"])


def all_profiles() -> list[AgentProfile]:
    """Distinct profiles in registration order (no alias duplicates)."""
    seen: set[str] = set()
    out: list[AgentProfile] = []
    for p in _PROFILES:
        if p.key not in seen:
            seen.add(p.key)
            out.append(p)
    return out


# Skill directories contributed by every known agent. `discover.py` unions
# these with a couple of framework-neutral conventions. Kept de-duplicated
# and order-stable so discovery output is deterministic.
def project_skill_dirs() -> tuple[str, ...]:
    dirs: list[str] = []
    for p in all_profiles():
        for d in p.project_dirs:
            if d not in dirs:
                dirs.append(d)
    for extra in ("skills",):          # bare project convention, no agent owns it
        if extra not in dirs:
            dirs.append(extra)
    return tuple(dirs)


def home_skill_dirs() -> tuple[str, ...]:
    dirs: list[str] = []
    for p in all_profiles():
        for d in p.home_dirs:
            if d not in dirs:
                dirs.append(d)
    return tuple(dirs)
