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


def test_fin_manifest_surfaces_permissions(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: s\ndescription: x\nfin_capabilities: [trade, transfer, tradng]\n---\nbody")
    found = {(f.severity, f.rule, f.evidence) for f in scan_skill_dir(d, Config())}
    assert ("INFO", "fin:moves_money", "trade") in found
    assert ("HIGH", "fin:capability_exceeds_policy", "transfer") in found
    assert ("LOW", "fin:unknown_capability", "tradng") in found


def test_finance_examples_have_no_high_findings():
    examples = Path(__file__).resolve().parents[2] / "firewall" / "examples" / "skills"
    for name in ("finance-quote-safe", "finance-paper-trader"):
        findings = scan_skill_dir(examples / name, Config())
        assert all(f.severity not in {"CRITICAL", "HIGH"} for f in findings), findings
