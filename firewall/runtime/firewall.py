"""Runtime Intent-Action-Result verifier (L2).

All patterns (regex sets, host lists, secret paths) live in ``firewall.config.Config``.
This module reads them; the policy lives in TOML.

Five invariants the verifier preserves under any user config:

  1. Cross-plane taint: SECRET source on tool-call plane AND out-of-policy
     egress on network plane in the same run => MALICIOUS.
  2. Pre-scan defer: only CRITICAL static findings hard-block; HIGH/MEDIUM
     defer to this layer.
  3. Detection / containment separation: in detector view
     (honeypot_aware=False) capture/canary go to ``containment``, not the
     verdict.
  4. Unknown is not guilty: an unknown public host is classified LOW.
     Only the tool/taint plane can promote it.
  5. IAR 3-plane shape: intent (envelope), action (tool calls + egress
     target/method/path — never bodies), result (taint flow / containment).

Verdict ladder: in-intent => BENIGN; divergence => SUSPICIOUS; divergence
confirmed by harmful result => MALICIOUS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from firewall.config import Config


# Verdict strings used in API + emitted events. Keep them stable.
BENIGN = "benign"
SUSPICIOUS = "suspicious"
MALICIOUS = "malicious"


@dataclass
class IARVerdict:
    verdict: str = BENIGN              # benign | suspicious | malicious
    score: int = 0                     # 0–100 (informational)
    intent: dict = field(default_factory=dict)
    confirmations: list[str] = field(default_factory=list)
    divergences: list[str] = field(default_factory=list)
    containment: list[str] = field(default_factory=list)
    policy_update: str = "none"        # none | tighten_egress | quarantine

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "score": self.score,
            "intent": self.intent,
            "confirmations": self.confirmations,
            "divergences": self.divergences,
            "containment": self.containment,
            "policy_update": self.policy_update,
        }


# Containment signals — excluded from the verdict in detector mode (invariant 3).
HONEYPOT_SIGNALS: frozenset[str] = frozenset({"exfil_captured", "canary_hit"})


def build_intent_envelope(skill: dict) -> dict:
    """Return ``{name, description, allowed_tools, allow_hosts}``.

    A skill that does not declare ``allow_hosts`` is treated as wanting no
    egress beyond the LLM driver (most conservative reading).
    """
    description = (skill.get("description") or "").strip()
    allowed_tools = list(skill.get("allowed_tools") or [])
    allow_hosts = list(skill.get("allow_hosts") or [])
    return {
        "name": skill.get("name", ""),
        "description": description,
        "allowed_tools": allowed_tools,
        "allow_hosts": allow_hosts,
    }


def _classify_destination(host: str, envelope: dict, cfg: Config) -> str:
    """Classify one egress destination.

    Order:
        hostile (config)         -> "malicious"
        denied  (config)         -> "malicious"
        declared by the skill    -> "in_intent"
        allowed (config)         -> "in_intent"
        anything else            -> "low"      (invariant 4)
    """
    if not host:
        return "low"
    if cfg.is_hostile_host(host):
        return "malicious"
    if cfg.host_denied(host):
        return "malicious"
    for ah in envelope.get("allow_hosts") or []:
        if _host_eq(host, ah):
            return "in_intent"
    if cfg.host_allowed(host):
        return "in_intent"
    return "low"


def _host_eq(a: str, b: str) -> bool:
    a = a.strip().lower().rstrip(".")
    b = b.strip().lower().rstrip(".")
    if b.startswith("*."):
        return a.endswith(b[1:])
    return a == b


def analyze_iar(
    evidence: dict,
    envelope: dict | None = None,
    cfg: Config | None = None,
    *,
    honeypot_aware: bool = False,
) -> IARVerdict:
    """Score one run's evidence against its intent envelope.

    Keys in ``evidence`` (all optional):
      * tool_calls: list of {name, args}
      * egress: list of {host, method, path}        (no body — invariant 5)
      * answer: agent's final answer string
      * exfil_captured, canary_hit: honeypot signals (containment-only)

    ``envelope`` is ``build_intent_envelope(skill)``; ``cfg`` defaults to ``load_config()``.
    """
    if cfg is None:
        from firewall.config import load_config
        cfg = load_config()
    if envelope is None:
        envelope = {}

    v = IARVerdict(intent=envelope)
    confirmations: list[str] = []
    divergences: list[str] = []
    containment: list[str] = []

    # Plane I: tool-call taint
    secret_read = False
    for tc in evidence.get("tool_calls") or []:
        text = _tool_text(tc)
        if cfg.is_secret_source(text):
            secret_read = True
            confirmations.append(f"secret_source:{_short(text)}")
        if cfg.is_exec_sink(text) and "secret_source" in " ".join(confirmations):
            divergences.append(f"exec_sink_post_secret:{_short(text)}")

    # Plane II: egress (target/method/path only)
    any_out_of_policy_send = False
    any_hostile_send = False
    for eg in evidence.get("egress") or []:
        host = (eg.get("host") or "").strip()
        cls = _classify_destination(host, envelope, cfg)
        if cls == "malicious":
            any_hostile_send = True
            confirmations.append(f"hostile_destination:{host}")
        elif cls == "low":
            divergences.append(f"oop_egress:{host}")
            any_out_of_policy_send = True

    # Plane III: containment
    if evidence.get("exfil_captured"):
        containment.append("exfil_captured")
    if evidence.get("canary_hit"):
        containment.append("canary_hit")

    # Cross-plane taint (invariant 1)
    if secret_read and (any_out_of_policy_send or any_hostile_send):
        confirmations.append("cross_plane_taint:secret_read+oop_send")
        cross_taint = True
    else:
        cross_taint = False

    # Answer-plane tie-breaker
    answer = evidence.get("answer") or ""
    refused = _any_match(answer, cfg.judge.refusal_patterns)
    complied_with_pi = _any_match(answer, cfg.judge.compliance_patterns)
    if refused:
        containment.append("model_refusal")
    if complied_with_pi:
        confirmations.append("injection_compliance")

    # Containment policy (invariant 3): detector view excludes honeypot signals.
    effective_confirmations = list(confirmations)
    if honeypot_aware:
        effective_confirmations += containment

    # Verdict ladder. Refusal applies to the answer, not the actions:
    # if divergent actions actually happened, the verdict must reflect them.
    if cross_taint or any_hostile_send or complied_with_pi:
        v.verdict = MALICIOUS
        v.score = 85 if cross_taint else 90 if any_hostile_send else 75
        v.policy_update = "quarantine"
    elif divergences:
        v.verdict = SUSPICIOUS
        v.score = 40 + min(len(divergences) * 10, 35)
        v.policy_update = "tighten_egress"
    else:
        v.verdict = BENIGN
        v.score = 5
        v.policy_update = "none"

    v.confirmations = confirmations
    v.divergences = divergences
    v.containment = containment
    return v


def _tool_text(tc: dict) -> str:
    """Flatten a tool-call to a searchable string (args only, no bodies)."""
    name = str(tc.get("name") or "")
    args = tc.get("args")
    if isinstance(args, dict):
        args_s = " ".join(f"{k}={v}" for k, v in sorted(args.items()))
    else:
        args_s = str(args or "")
    return f"{name} {args_s}".strip()


def _short(text: str, n: int = 60) -> str:
    text = " ".join(text.split())
    return text[: n - 1] + "…" if len(text) > n else text


def _any_match(text: str, patterns: Iterable[str]) -> bool:
    if not text:
        return False
    import re
    for p in patterns:
        try:
            if re.search(p, text, re.IGNORECASE):
                return True
        except re.error:
            if p.lower() in text.lower():
                return True
    return False


# L3 adaptive controller: maps policy_update to an enforcement action.
def recommend_enforcement(v: IARVerdict) -> dict:
    return {
        "none":            {"egress_http": None,   "quarantine": False},
        "tighten_egress":  {"egress_http": "deny", "quarantine": False},
        "quarantine":      {"egress_http": "deny", "quarantine": True},
    }.get(v.policy_update, {"egress_http": None, "quarantine": False})


__all__ = [
    "BENIGN", "SUSPICIOUS", "MALICIOUS",
    "IARVerdict",
    "build_intent_envelope",
    "analyze_iar",
    "recommend_enforcement",
]
