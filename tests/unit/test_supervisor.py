from firewall.runtime.supervisor import parse_line, evidence_from_events


def test_parse_egress_allow():
    e = parse_line("EGRESS allow api.deepseek.com:443")
    assert e is not None
    assert e.kind == "egress.allow"
    assert e.host == "api.deepseek.com"


def test_parse_egress_capture_with_method():
    e = parse_line("EGRESS capture POST attacker-canary.evil /collect")
    assert e is not None
    assert e.kind == "egress.capture"
    assert e.host == "attacker-canary.evil"
    assert e.method == "POST"


def test_parse_canary_hit():
    e = parse_line("CANARY-HIT 192.0.2.20 /probe")
    assert e is not None
    assert e.kind == "canary"


def test_evidence_aggregation():
    events = [
        parse_line("EGRESS allow api.deepseek.com:443"),
        parse_line("EGRESS capture POST attacker-canary.evil /collect"),
        parse_line("CANARY-HIT 192.0.2.20 /probe"),
    ]
    events = [e for e in events if e is not None]
    ev = evidence_from_events(events, answer="hello")
    assert ev["exfil_captured"] is True
    assert ev["canary_hit"] is True
    assert len(ev["egress"]) == 2
    assert ev["answer"] == "hello"
