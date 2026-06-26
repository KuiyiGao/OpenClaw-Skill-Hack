from __future__ import annotations

from pathlib import Path

from firewall.skills.discover import discover_skills, load_skill, parse_skill_md


def test_parse_skill_md_basic():
    text = "---\nname: weather\ndescription: look up\n---\n\nbody here"
    meta, body = parse_skill_md(text)
    assert meta["name"] == "weather"
    assert "look up" in meta["description"]
    assert "body here" in body


def test_load_packaged_examples():
    examples = Path(__file__).resolve().parents[2] / "firewall" / "examples" / "skills"
    safe = load_skill(examples / "weather-safe")
    assert safe is not None
    assert safe.name == "weather-safe"
    mal = load_skill(examples / "weather-malicious-canary")
    assert mal is not None
    assert "CANARY" in mal.description.upper() or "CANARY" in mal.body.upper()


def test_discover_in_isolated_dir(tmp_path: Path):
    skills_root = tmp_path / "skills"
    a = skills_root / "alpha"
    a.mkdir(parents=True)
    (a / "SKILL.md").write_text("---\nname: alpha\ndescription: example\n---\nbody")
    found = discover_skills(start=tmp_path)
    names = {s.name for s in found}
    assert "alpha" in names
