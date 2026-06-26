"""User-editable configuration for the firewall.

All runtime patterns (regex sets, host lists, secret paths, judge prompts)
load from ``~/.config/firewall/config.toml`` (XDG; macOS uses
``~/Library/Application Support/firewall/``). ``firewall.runtime`` is
policy-free; this file is the policy.
"""

from __future__ import annotations

import os
import sys
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # py310
    import tomli as tomllib  # type: ignore[import-not-found, no-redef]

from platformdirs import user_config_dir, user_state_dir, user_cache_dir


_APP = "firewall"


def config_dir() -> Path:
    return Path(user_config_dir(_APP))


def state_dir() -> Path:
    return Path(user_state_dir(_APP))


def cache_dir() -> Path:
    return Path(user_cache_dir(_APP))


def config_path() -> Path:
    return config_dir() / "config.toml"


@dataclass
class DriverConfig:
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    api_key_env: str = "DEEPSEEK_API_KEY"
    timeout_s: int = 30
    max_retries: int = 2


@dataclass
class PolicyConfig:
    # strict (block on first taint), balanced (defer if no second-plane signal),
    # observe (record only — never block).
    mode: str = "balanced"
    defer_on_uncertain: bool = True
    canary_on_secret_read: bool = True


@dataclass
class EgressConfig:
    allow_hosts: list[str] = field(default_factory=lambda: [
        "api.deepseek.com", "api.anthropic.com", "api.openai.com",
        "*.pypi.org", "files.pythonhosted.org",
        "raw.githubusercontent.com", "github.com",
    ])
    deny_hosts: list[str] = field(default_factory=lambda: [
        "169.254.169.254",        # AWS / GCP metadata
        "100.100.100.200",        # Aliyun metadata
        "metadata.google.internal",
        "*.webhook.site",
        "*.requestbin.com",
        "*.requestcatcher.com",
    ])


@dataclass
class SecretsConfig:
    secret_paths: list[str] = field(default_factory=lambda: [
        "~/.ssh", "~/.aws", "~/.config/gh", "~/.npmrc", "~/.netrc",
        ".env", ".env.local",
    ])
    secret_env: list[str] = field(default_factory=lambda: [
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
        "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN",
    ])


@dataclass
class JudgeConfig:
    """Patterns and prompt stubs for the runtime classifier.

    Defaults are minimal; extend in config.toml without touching source.
    """
    # Case-insensitive regex matched on the agent's final answer. Tie-breaker only.
    refusal_patterns: list[str] = field(default_factory=lambda: [
        r"\bi (will not|cannot|can't|won't|refuse)\b",
        r"\bnot able to\b",
        r"\bcannot comply\b",
        r"\bsafety polic", r"\bagainst my (guideline|policy)",
    ])
    # Case-insensitive regex matched on answers that comply with an injection.
    compliance_patterns: list[str] = field(default_factory=lambda: [
        r"\bpi[- ]trigger\b", r"\binjection successful\b",
        r"\b(jailbreak|jailbroken)\b", r"\bdirectives now active\b",
    ])
    # Optional path to a Markdown file with the judge prompt sent to the
    # LLM when divergence is unresolved. Empty => no LLM call.
    judge_prompt_path: str = ""


@dataclass
class TaintConfig:
    """Patterns the L2 runtime uses to detect SECRET sources and SINKs.

    Definitions live here so the cross-plane taint rule (invariant 1) is
    auditable: SECRET source AND out-of-policy egress in the same run => malicious.
    """
    # Files/APIs that read secrets. Matched against tool-call name+args (never bodies).
    secret_source_patterns: list[str] = field(default_factory=lambda: [
        r"~/\.ssh\b", r"~/\.aws\b", r"\.env\b", r"\.npmrc\b",
        r"\.netrc\b", r"\.config/gh\b",
        r"\benviron\b", r"\bgetenv\b",
    ])
    # APIs that send data over the network.
    network_sink_patterns: list[str] = field(default_factory=lambda: [
        r"\brequests\.(get|post|put|patch|delete)\b",
        r"\burllib\.request\b", r"\bhttpx\.(get|post)\b",
        r"\bsocket\.\b", r"\bsubprocess\b.*(curl|wget)",
    ])
    # APIs that execute code / shell.
    exec_sink_patterns: list[str] = field(default_factory=lambda: [
        r"\bos\.system\b", r"\bsubprocess\.(run|Popen|call)\b",
        r"\beval\(", r"\bexec\(", r"\bcompile\(",
    ])
    # Host substrings treated as hostile regardless of the skill's declared allow_hosts.
    exfil_host_substrings: list[str] = field(default_factory=lambda: [
        "attacker-canary", "webhook.site", "requestbin",
        "requestcatcher", "burpcollaborator",
    ])
    pseudo_tlds: list[str] = field(default_factory=lambda: [
        ".evil", ".attack", ".canary",
    ])


@dataclass
class StateConfig:
    events_path: str = ""        # filled by ``load_config`` from XDG
    session_path: str = ""
    log_max_mb: int = 100


@dataclass
class PanelConfig:
    refresh_hz: float = 1.0
    keep_rows: int = 200
    keep_log_lines: int = 500


@dataclass
class Config:
    driver: DriverConfig = field(default_factory=DriverConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    egress: EgressConfig = field(default_factory=EgressConfig)
    secrets: SecretsConfig = field(default_factory=SecretsConfig)
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    taint: TaintConfig = field(default_factory=TaintConfig)
    state: StateConfig = field(default_factory=StateConfig)
    panel: PanelConfig = field(default_factory=PanelConfig)
    # USD per 1M tokens, keyed by "provider/model". Unknown pairs render as "$ —".
    prices: dict[str, dict[str, float]] = field(default_factory=lambda: {
        "deepseek/deepseek-chat": {"input": 0.27, "output": 1.10},
        "anthropic/claude-opus-4-7": {"input": 15.0, "output": 75.0},
        "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    })

    def host_allowed(self, host: str) -> bool:
        return _host_match(host, self.egress.allow_hosts)

    def host_denied(self, host: str) -> bool:
        return _host_match(host, self.egress.deny_hosts)

    def is_secret_source(self, text: str) -> bool:
        return _any_pattern_match(text, self.taint.secret_source_patterns)

    def is_network_sink(self, text: str) -> bool:
        return _any_pattern_match(text, self.taint.network_sink_patterns)

    def is_exec_sink(self, text: str) -> bool:
        return _any_pattern_match(text, self.taint.exec_sink_patterns)

    def is_hostile_host(self, host: str) -> bool:
        host_l = host.lower()
        if any(s in host_l for s in self.taint.exfil_host_substrings):
            return True
        return any(host_l.endswith(t) for t in self.taint.pseudo_tlds)


def _host_match(host: str, patterns: list[str]) -> bool:
    h = host.strip().lower().rstrip(".")
    for p in patterns:
        p = p.strip().lower().rstrip(".")
        if p.startswith("*."):
            if h.endswith(p[1:]):
                return True
        elif h == p:
            return True
    return False


def _any_pattern_match(text: str, patterns: list[str]) -> bool:
    for p in patterns:
        try:
            if re.search(p, text, re.IGNORECASE):
                return True
        except re.error:
            if p.lower() in text.lower():
                return True
    return False


def _fill_state_defaults(cfg: Config) -> Config:
    if not cfg.state.events_path:
        cfg.state.events_path = str(state_dir() / "events.jsonl")
    if not cfg.state.session_path:
        cfg.state.session_path = str(state_dir() / "session.json")
    return cfg


def load_config(path: Path | str | None = None) -> Config:
    p = Path(path) if path else config_path()
    cfg = Config()
    if not p.exists():
        return _fill_state_defaults(cfg)
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    for section in ("driver", "policy", "egress", "secrets",
                    "judge", "taint", "state", "panel"):
        if section in data and isinstance(data[section], dict):
            target = getattr(cfg, section)
            for k, v in data[section].items():
                if hasattr(target, k):
                    setattr(target, k, v)
    if "prices" in data and isinstance(data["prices"], dict):
        cfg.prices.update(data["prices"])
    return _fill_state_defaults(cfg)


DEFAULT_CONFIG_TOML = """# ~/.config/firewall/config.toml — runtime behavioral firewall for Agent Skills.
# Everything the runtime decides on lives in THIS file; the code is policy-free.
# Comments explain the trade-offs. Edit, version-control, ship with your project.

[driver]
# Which LLM the runtime calls when it needs a tie-breaker judge.
# `api_key_env` is the NAME of an env var (NOT the key itself).
provider     = "deepseek"
base_url     = "https://api.deepseek.com/v1"
model        = "deepseek-chat"
api_key_env  = "DEEPSEEK_API_KEY"
timeout_s    = 30
max_retries  = 2

[policy]
# strict  : block on first taint signal even without confirmation
# balanced: block only on cross-plane taint (recommended default)
# observe : never block — record only (use during onboarding)
mode = "balanced"
defer_on_uncertain     = true
canary_on_secret_read  = true

[egress]
# Hosts the sandboxed skill is allowed to reach. Suffix wildcards (*.example.com).
allow_hosts = [
  "api.deepseek.com",
  "api.anthropic.com",
  "api.openai.com",
  "*.pypi.org",
  "files.pythonhosted.org",
  "raw.githubusercontent.com",
  "github.com",
]
# Hosts that are NEVER reachable. Cloud metadata + canary services pre-loaded.
deny_hosts = [
  "169.254.169.254",
  "100.100.100.200",
  "metadata.google.internal",
  "*.webhook.site",
  "*.requestbin.com",
  "*.requestcatcher.com",
]

[secrets]
# Filesystem paths the firewall treats as SECRET sources for taint analysis.
secret_paths = [
  "~/.ssh", "~/.aws", "~/.config/gh", "~/.npmrc", "~/.netrc",
  ".env", ".env.local",
]
secret_env = [
  "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
  "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN",
]

[judge]
# Patterns (case-insensitive regex) the L2 verifier uses on the agent's answer.
# Keep tight: 4-6 entries each. These are used only as TIE-BREAKERS when the
# cross-plane taint rule is ambiguous.
refusal_patterns    = [ "\\\\bi (will not|cannot|can't|won't|refuse)\\\\b", "\\\\bnot able to\\\\b", "\\\\bsafety polic" ]
compliance_patterns = [ "\\\\bpi[- ]trigger\\\\b", "\\\\binjection successful\\\\b" ]
# Optional path to a Markdown file with YOUR judge prompt. If empty, no LLM
# call is made (the L2 verifier is fully deterministic by default).
judge_prompt_path = ""

[taint]
# What counts as a SECRET source (substring/regex match on the tool-call text).
secret_source_patterns = [
  "~/\\\\.ssh\\\\b", "~/\\\\.aws\\\\b", "\\\\.env\\\\b",
  "\\\\benviron\\\\b", "\\\\bgetenv\\\\b",
]
# What counts as a network SINK.
network_sink_patterns = [
  "\\\\brequests\\\\.(get|post|put|patch|delete)\\\\b",
  "\\\\burllib\\\\.request\\\\b", "\\\\bhttpx\\\\.(get|post)\\\\b",
  "\\\\bsocket\\\\.\\\\b",
]
# What counts as an exec SINK.
exec_sink_patterns = [
  "\\\\bos\\\\.system\\\\b", "\\\\bsubprocess\\\\.(run|Popen|call)\\\\b",
  "\\\\beval\\\\(", "\\\\bexec\\\\(",
]
# Host substrings that read as obviously hostile no matter what the skill declared.
exfil_host_substrings = [ "attacker-canary", "webhook.site", "requestbin" ]
# Pseudo-TLDs used in CANARY testing.
pseudo_tlds = [ ".evil", ".attack", ".canary" ]

[panel]
refresh_hz       = 1.0
keep_rows        = 200
keep_log_lines   = 500

# Token prices in USD per 1M tokens, keyed by "provider/model".
[prices."deepseek/deepseek-chat"]
input  = 0.27
output = 1.10

[prices."anthropic/claude-opus-4-7"]
input  = 15.0
output = 75.0
"""


def init_default(path: Path | str | None = None, *, overwrite: bool = False) -> Path:
    p = Path(path) if path else config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and not overwrite:
        return p
    p.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return p


__all__ = [
    "Config", "DriverConfig", "PolicyConfig", "EgressConfig",
    "SecretsConfig", "JudgeConfig", "TaintConfig", "StateConfig", "PanelConfig",
    "load_config", "init_default",
    "config_dir", "state_dir", "cache_dir", "config_path",
    "DEFAULT_CONFIG_TOML",
]
