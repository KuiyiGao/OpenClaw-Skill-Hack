"""Financial capability plane: what a request or tool call can do with money.

The vocabulary (four capabilities, ordered by risk) lives here. Which hosts,
routes and tool names map to which capability is policy, in the ``[finance]``
section of config.toml.

A skill's *effective* capabilities are the ones it declares in SKILL.md
(``fin_capabilities``) that ``finance.allowed_capabilities`` also permits.
Invariants this plane adds to the L2 verifier:

  F1. Money movement is never implicit: an exactly classified trade/transfer
      outside the effective capabilities => MALICIOUS.
  F2. Ambiguity is not guilt: a host-level classification (a CONNECT, route
      not visible) is at most a divergence. Only another plane promotes it.
  F3. Account data is a taint source: exact account access plus an
      out-of-policy send in the same run => MALICIOUS (extends invariant 1).
  F4. Paper means paper: with ``environment = "paper"`` the proxy denies
      ``live_hosts`` in every policy mode (``Config.blocks_live_trading``).
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

from firewall.config import Config, _host_match


MARKET_DATA = "market_data"
ACCOUNT_READ = "account_read"
TRADE = "trade"
TRANSFER = "transfer"

# Low -> high risk. TRADE and above move money.
CAPABILITIES: tuple[str, ...] = (MARKET_DATA, ACCOUNT_READ, TRADE, TRANSFER)


def rank(capability: str) -> int:
    """Risk rank; -1 for a name outside the vocabulary."""
    try:
        return CAPABILITIES.index(capability)
    except ValueError:
        return -1


def moves_money(capability: str) -> bool:
    return rank(capability) >= rank(TRADE)


@dataclass(frozen=True)
class FinAction:
    capability: str
    exact: bool     # False: host-level upper bound, the route was not visible
    target: str     # host, or "tool:<name>"


def _rules(rules) -> list[dict]:
    """Well-formed rules only; ``catalog_problems`` reports the rest."""
    return [r for r in rules or [] if isinstance(r, dict)]


def _rule_hosts(rule: dict) -> list[str]:
    hosts = rule.get("host") or []
    return [hosts] if isinstance(hosts, str) else [str(h) for h in hosts]


def host_capabilities(host: str, cfg: Config) -> set[str]:
    """Every capability the catalog says ``host`` can serve."""
    return {
        str(r.get("capability"))
        for r in _rules(cfg.finance.endpoints)
        if rank(str(r.get("capability"))) >= 0 and _host_match(host, _rule_hosts(r))
    }


def effective_capabilities(envelope: dict, cfg: Config) -> set[str]:
    declared = set(envelope.get("fin_capabilities") or [])
    return declared & set(cfg.finance.allowed_capabilities)


def classify_request(host: str, method: str, path: str, cfg: Config) -> FinAction | None:
    """Classify one egress request against ``finance.endpoints``.

    Most specific rule wins: longest path pattern, then a rule naming the
    method; ties go to the higher capability. A CONNECT shows no method/path,
    so only host-level rules match it. A catalog host with no matching rule
    falls back to the highest capability it serves.
    """
    method = (method or "").upper()
    path = (path or "").split("?", 1)[0].lower()
    visible = method not in ("", "CONNECT") and path.startswith("/")
    best: FinAction | None = None
    best_key: tuple[int, int, int] | None = None
    for rule in _rules(cfg.finance.endpoints):
        cap = str(rule.get("capability") or "")
        if rank(cap) < 0 or not _host_match(host, _rule_hosts(rule)):
            continue
        r_method = str(rule.get("method") or "").upper()
        r_path = str(rule.get("path") or "").lower()
        routed = bool(r_method or r_path)
        if routed and not (
            visible
            and (not r_method or r_method == method)
            and (not r_path or fnmatch.fnmatchcase(path, r_path))
        ):
            continue
        key = (len(re.sub(r"[*?\[\]]", "", r_path)), int(bool(r_method)), rank(cap))
        if best_key is None or key > best_key:
            best_key, best = key, FinAction(cap, exact=routed, target=host)
    if best is None:
        served = host_capabilities(host, cfg)
        if served:
            best = FinAction(max(served, key=rank), exact=False, target=host)
    return best


def classify_tool(name: str, cfg: Config) -> FinAction | None:
    """Classify a tool call by its NAME against ``finance.tool_capabilities``."""
    if not name:
        return None
    best: FinAction | None = None
    for rule in _rules(cfg.finance.tool_capabilities):
        pattern = str(rule.get("pattern") or "")
        cap = str(rule.get("capability") or "")
        if not pattern or rank(cap) < 0:
            continue
        try:
            hit = re.search(pattern, name, re.IGNORECASE) is not None
        except re.error:
            hit = pattern.lower() in name.lower()
        if hit and (best is None or rank(cap) > rank(best.capability)):
            best = FinAction(cap, exact=True, target=f"tool:{name}")
    return best


def catalog_problems(cfg: Config) -> list[str]:
    """Entries in ``[finance]`` that can never match as written."""
    problems: list[str] = []
    for cap in cfg.finance.allowed_capabilities or []:
        if rank(str(cap)) < 0:
            problems.append(f"allowed_capabilities: unknown capability {cap!r}")
    for section, key in (("endpoints", "host"), ("tool_capabilities", "pattern")):
        for i, rule in enumerate(getattr(cfg.finance, section) or []):
            where = f"{section}[{i}]"
            if not isinstance(rule, dict):
                problems.append(f"{where}: not a table")
                continue
            if rank(str(rule.get("capability"))) < 0:
                problems.append(f"{where}: unknown capability {rule.get('capability')!r}")
            if not rule.get(key):
                problems.append(f"{where}: missing {key}")
            elif key == "pattern":
                try:
                    re.compile(str(rule[key]))
                except re.error as e:
                    problems.append(f"{where}: bad regex ({e})")
    return problems


@dataclass
class FinAssessment:
    confirmations: list[str] = field(default_factory=list)
    divergences: list[str] = field(default_factory=list)
    money_moved: bool = False       # F1 fired
    account_exposed: bool = False   # F3 source present


def assess(evidence: dict, envelope: dict, cfg: Config) -> FinAssessment:
    """Judge one run's financial actions against the skill's effective capabilities."""
    out = FinAssessment()
    declared = set(envelope.get("fin_capabilities") or [])
    effective = effective_capabilities(envelope, cfg)
    actions: list[FinAction] = []
    for eg in evidence.get("egress") or []:
        host = (eg.get("host") or "").strip()
        if cfg.blocks_live_trading(host):
            _add(out.divergences, f"fin_live_in_paper:{host}")
        a = classify_request(host, eg.get("method") or "", eg.get("path") or "", cfg)
        if a is not None:
            actions.append(a)
    for tc in evidence.get("tool_calls") or []:
        a = classify_tool(str(tc.get("name") or ""), cfg)
        if a is not None:
            actions.append(a)

    for a in actions:
        if a.exact and rank(a.capability) >= rank(ACCOUNT_READ):
            out.account_exposed = True
        if a.capability in effective:
            continue
        if not a.exact:
            _add(out.divergences, f"fin_ambiguous:{a.capability}@{a.target}")
            continue
        why = "fin_forbidden" if a.capability in declared else "fin_undeclared"
        label = f"{why}:{a.capability}@{a.target}"
        if moves_money(a.capability):
            _add(out.confirmations, label)
            out.money_moved = True
        else:
            _add(out.divergences, label)
    return out


def _add(items: list[str], label: str) -> None:
    if label not in items:
        items.append(label)


__all__ = [
    "MARKET_DATA", "ACCOUNT_READ", "TRADE", "TRANSFER", "CAPABILITIES",
    "rank", "moves_money",
    "FinAction", "FinAssessment",
    "host_capabilities", "effective_capabilities",
    "classify_request", "classify_tool", "assess", "catalog_problems",
]
