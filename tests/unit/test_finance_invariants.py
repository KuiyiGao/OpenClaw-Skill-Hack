"""Financial-plane invariants F1-F4 (see ``firewall/finance/capabilities.py``).

Hostile behaviour is expressed as synthetic evidence dicts, as in
``test_firewall_invariants.py``: no test runs a skill or reaches the network.
"""

from __future__ import annotations

import socket
import threading
from dataclasses import asdict
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # py310
    import tomli as tomllib  # type: ignore[import-not-found, no-redef]

from firewall.config import DEFAULT_CONFIG_TOML, Config, FinanceConfig
from firewall.finance.capabilities import catalog_problems, classify_request, classify_tool
from firewall.runtime.firewall import (
    BENIGN, MALICIOUS, SUSPICIOUS,
    analyze_iar, build_intent_envelope,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "firewall" / "examples" / "skills"


@pytest.fixture
def cfg() -> Config:
    return Config()


def _skill(*caps: str) -> dict:
    return build_intent_envelope(
        {"name": "fin", "description": "x", "fin_capabilities": list(caps)})


def _ev(*, tool_calls=None, egress=None) -> dict:
    return {"tool_calls": tool_calls or [], "egress": egress or [], "answer": ""}


def _req(host: str, method: str = "CONNECT", path: str = "") -> dict:
    """One egress record as the proxy logs it; a CONNECT's path is host:port."""
    return {"host": host, "method": method, "path": path or f"{host}:443"}


# ------------------------------------------------------------------ F1
def test_undeclared_money_movement_is_malicious(cfg):
    """An exact trade the skill never declared => MALICIOUS, on either plane."""
    envelope = _skill("market_data")
    via_route = _ev(egress=[_req("paper-api.alpaca.markets", "POST", "/v2/orders")])
    via_tool = _ev(tool_calls=[
        {"name": "mcp__alpaca__place_stock_order", "args": {"symbol": "AAPL", "qty": 1}},
    ])
    for evidence in (via_route, via_tool):
        v = analyze_iar(evidence, envelope, cfg)
        assert v.verdict == MALICIOUS, v.to_dict()
        assert any(c.startswith("fin_undeclared:trade@") for c in v.confirmations)


def test_declared_but_forbidden_money_movement_is_malicious(cfg):
    """Declaring a capability the policy forbids does not make it effective."""
    cfg.finance.environment = "live"
    envelope = _skill("account_read", "transfer")  # default policy excludes transfer
    evidence = _ev(egress=[
        _req("api.binance.com", "POST", "/sapi/v1/capital/withdraw/apply"),
    ])
    v = analyze_iar(evidence, envelope, cfg)
    assert v.verdict == MALICIOUS
    assert "fin_forbidden:transfer@api.binance.com" in v.confirmations


def test_declared_trading_within_policy_is_benign(cfg):
    envelope = _skill("market_data", "account_read", "trade")
    evidence = _ev(egress=[
        _req("paper-api.alpaca.markets", "GET", "/v2/account"),
        _req("paper-api.alpaca.markets", "POST", "/v2/orders"),
        _req("data.alpaca.markets"),
    ])
    v = analyze_iar(evidence, envelope, cfg)
    assert v.verdict == BENIGN, v.to_dict()


# ------------------------------------------------------------------ F2
def test_host_level_financial_ambiguity_is_not_guilt(cfg):
    """A CONNECT hides the route: the host *could* trade => SUSPICIOUS, never MALICIOUS."""
    envelope = _skill("market_data", "account_read")
    v = analyze_iar(_ev(egress=[_req("paper-api.alpaca.markets")]), envelope, cfg)
    assert v.verdict == SUSPICIOUS
    assert "fin_ambiguous:trade@paper-api.alpaca.markets" in v.divergences


def test_reading_own_account_over_https_is_not_exfiltration(cfg):
    """A read-only skill talking to the broker it declared is not an out-of-policy send."""
    envelope = _skill("market_data", "account_read")
    evidence = _ev(
        tool_calls=[{"name": "mcp__alpaca__get_account_info", "args": {}}],
        egress=[_req("paper-api.alpaca.markets")],
    )
    v = analyze_iar(evidence, envelope, cfg)
    assert v.verdict == SUSPICIOUS
    assert not any(c.startswith("cross_plane_taint") for c in v.confirmations)


# ------------------------------------------------------------------ F3
def test_account_data_plus_oop_send_is_malicious(cfg):
    """Exact account access + an out-of-policy send in one run => MALICIOUS."""
    envelope = _skill("account_read")
    evidence = _ev(egress=[
        _req("paper-api.alpaca.markets", "GET", "/v2/positions"),
        _req("unknown.example.com", "POST", "/collect"),
    ])
    v = analyze_iar(evidence, envelope, cfg)
    assert v.verdict == MALICIOUS
    assert "cross_plane_taint:account_data+oop_send" in v.confirmations


def test_unrelated_financial_host_still_counts_as_oop_send(cfg):
    """Invariant 1 keeps working when the send goes to a broker the skill never declared."""
    envelope = build_intent_envelope({"name": "weather", "description": "weather"})
    evidence = _ev(
        tool_calls=[{"name": "Read", "args": {"path": "~/.aws/credentials"}}],
        egress=[_req("testnet.binance.vision")],
    )
    v = analyze_iar(evidence, envelope, cfg)
    assert v.verdict == MALICIOUS
    assert "cross_plane_taint:secret_read+oop_send" in v.confirmations


# ------------------------------------------------------------------ F4
def _status_line(sock: socket.socket) -> bytes:
    buf = b""
    while b"\r\n" not in buf:
        chunk = sock.recv(256)
        if not chunk:
            break
        buf += chunk
    return buf.split(b"\r\n", 1)[0]


def test_paper_mode_denies_live_hosts_even_in_observe(tmp_path, monkeypatch):
    """environment=paper denies live_hosts at the proxy before policy.mode is read."""
    from firewall.runtime import egress_proxy as ep
    from firewall.runtime.events import EventEmitter

    cfg = Config()
    cfg.policy.mode = "observe"  # the mode that otherwise never blocks
    events = tmp_path / "events.jsonl"
    monkeypatch.setattr(ep, "config_path", lambda: tmp_path / "absent.toml")
    monkeypatch.setattr(ep._Handler, "live_cfg", ep._LiveConfig(cfg), raising=False)
    monkeypatch.setattr(ep._Handler, "emitter", EventEmitter(events), raising=False)

    srv = ep._ThreadedServer(("127.0.0.1", 0), ep._Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        port = srv.server_address[1]
        for request in (
            b"CONNECT api.alpaca.markets:443 HTTP/1.1\r\nHost: api.alpaca.markets:443\r\n\r\n",
            b"GET http://api.alpaca.markets/v2/account HTTP/1.1\r\nHost: api.alpaca.markets\r\n\r\n",
        ):
            with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
                s.sendall(request)
                assert b" 403 " in _status_line(s)
    finally:
        srv.shutdown()
        srv.server_close()
    assert events.read_text().count('"egress.deny"') == 2


def test_unknown_environment_fails_closed(cfg):
    cfg.finance.environment = "production"  # not "live" => treated as paper
    assert cfg.blocks_live_trading("api.alpaca.markets")
    assert not cfg.blocks_live_trading("paper-api.alpaca.markets")
    cfg.finance.environment = "live"
    assert not cfg.blocks_live_trading("api.alpaca.markets")


def test_live_host_attempt_in_paper_mode_is_a_divergence(cfg):
    envelope = _skill("market_data", "account_read", "trade")
    v = analyze_iar(_ev(egress=[_req("api.alpaca.markets")]), envelope, cfg)
    assert v.verdict == SUSPICIOUS
    assert "fin_live_in_paper:api.alpaca.markets" in v.divergences


# ------------------------------------------------------- catalog / policy
@pytest.mark.parametrize("host,method,path,cap,exact", [
    ("paper-api.alpaca.markets", "POST", "/v2/orders", "trade", True),
    ("paper-api.alpaca.markets", "GET", "/v2/orders?status=open", "account_read", True),
    ("paper-api.alpaca.markets", "DELETE", "/v2/positions/AAPL", "trade", True),
    ("paper-api.alpaca.markets", "CONNECT", "paper-api.alpaca.markets:443", "trade", False),
    ("data.alpaca.markets", "CONNECT", "data.alpaca.markets:443", "market_data", False),
    ("api.binance.com", "GET", "/api/v3/klines", "market_data", True),
    ("api.binance.com", "GET", "/api/v3/account", "account_read", True),
    ("api.binance.com", "GET", "/api/v3/openOrders", "account_read", True),
    ("api.binance.com", "POST", "/sapi/v1/capital/withdraw/apply", "transfer", True),
    ("api.binance.com", "POST", "/sapi/v1/not-in-catalog", "transfer", False),
])
def test_catalog_most_specific_rule_wins(cfg, host, method, path, cap, exact):
    a = classify_request(host, method, path, cfg)
    assert a is not None
    assert (a.capability, a.exact) == (cap, exact)


def test_non_financial_host_is_unclassified(cfg):
    assert classify_request("api.deepseek.com", "POST", "/v1/chat/completions", cfg) is None


def test_catalog_host_without_host_rule_uses_highest_capability(cfg):
    cfg.finance.endpoints = [
        {"host": "broker.example", "method": "POST", "path": "/orders", "capability": "trade"},
        {"host": "broker.example", "method": "GET", "path": "/quotes", "capability": "market_data"},
    ]
    a = classify_request("broker.example", "CONNECT", "broker.example:443", cfg)
    assert a is not None
    assert (a.capability, a.exact) == ("trade", False)


@pytest.mark.parametrize("name,cap", [
    ("mcp__alpaca__place_stock_order", "trade"),
    ("cancel_all_orders", "trade"),
    ("close_all_positions", "trade"),
    ("binance_withdraw", "transfer"),
    ("get_account_info", "account_read"),
    ("get_stock_latest_quote", "market_data"),
])
def test_tool_names_classify(cfg, name, cap):
    a = classify_tool(name, cfg)
    assert a is not None and a.capability == cap and a.exact


def test_generic_tools_are_not_financial(cfg):
    for name in ("Read", "Write", "Bash", "WebFetch", "Grep"):
        assert classify_tool(name, cfg) is None, name


def test_catalog_problems_flags_rules_that_can_never_match(cfg):
    assert catalog_problems(cfg) == []
    cfg.finance.allowed_capabilities = ["market_data", "Trade"]
    cfg.finance.endpoints = [
        {"host": "broker.example", "capability": "trdae"},
        "not-a-table",
        {"capability": "trade"},
    ]
    cfg.finance.tool_capabilities = [{"pattern": "(unclosed", "capability": "trade"}]
    assert len(catalog_problems(cfg)) == 5


def test_malformed_rules_do_not_crash_the_verifier(cfg):
    cfg.finance.endpoints = ["not-a-table", {"host": "broker.example", "capability": "trade"}]
    cfg.finance.tool_capabilities = ["not-a-table"]
    evidence = _ev(egress=[_req("broker.example")], tool_calls=[{"name": "place_order"}])
    v = analyze_iar(evidence, _skill("market_data"), cfg)
    assert v.verdict == SUSPICIOUS
    assert "fin_ambiguous:trade@broker.example" in v.divergences


def test_finance_template_matches_dataclass_defaults():
    """What `firewall config init` writes must be what the tests exercise."""
    assert tomllib.loads(DEFAULT_CONFIG_TOML)["finance"] == asdict(FinanceConfig())


# ------------------------------------------------------ end-to-end replay
def test_watch_replays_proxy_jsonl(tmp_path, monkeypatch):
    """`firewall watch` judges the events.jsonl the proxy writes, finance plane included."""
    from typer.testing import CliRunner
    from firewall import cli

    conf = tmp_path / "config.toml"
    conf.write_text(f'[state]\nevents_path = "{(tmp_path / "events.jsonl").as_posix()}"\n')
    monkeypatch.setattr(cli, "config_path", lambda: conf)
    log = tmp_path / "run.jsonl"
    log.write_text("\n".join([
        '{"ts": "t", "kind": "info", "message": "egress-proxy listening"}',
        '{"ts": "t", "kind": "egress.allow", "host": "data.alpaca.markets", '
        '"method": "GET", "path": "/v2/stocks/AAPL/quotes/latest"}',
        '{"ts": "t", "kind": "egress.allow", "host": "paper-api.alpaca.markets", '
        '"method": "POST", "path": "/v2/orders"}',
    ]) + "\n")
    result = CliRunner().invoke(
        cli.app, ["watch", str(EXAMPLES / "finance-quote-safe"), "--log-file", str(log)])
    assert result.exit_code == 0, result.output
    assert "MALICIOUS" in result.output
    assert "fin_undeclared:trade@paper-api.alpaca.markets" in result.output
