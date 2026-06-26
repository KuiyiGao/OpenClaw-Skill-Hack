from pathlib import Path

from firewall.config import Config
from firewall.gate.static_scanner import scan_skill_dir


def test_safe_example_has_no_critical():
    examples = Path(__file__).resolve().parents[2] / "firewall" / "examples" / "skills"
    findings = scan_skill_dir(examples / "weather-safe", Config())
    assert all(f.severity not in {"CRITICAL", "HIGH"} for f in findings), findings


def test_canary_example_flags_hostile_host():
    examples = Path(__file__).resolve().parents[2] / "firewall" / "examples" / "skills"
    findings = scan_skill_dir(examples / "weather-malicious-canary", Config())
    rules = {f.rule for f in findings}
    # The exfil URL `attacker-canary.evil` matches a default exfil substring.
    assert any("hostile_host_literal" == r for r in rules), findings
