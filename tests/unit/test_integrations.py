"""The OpenClaw Node bootstrap must ship in the wheel and resolve from CLI."""

from __future__ import annotations

from pathlib import Path


def test_bootstrap_file_exists():
    pkg = Path(__file__).resolve().parents[2] / "firewall"
    bootstrap = pkg / "integrations" / "openclaw" / "proxy-bootstrap.js"
    assert bootstrap.exists(), bootstrap
    text = bootstrap.read_text()
    # The two undici primitives we depend on must appear verbatim.
    assert "setGlobalDispatcher" in text
    assert "ProxyAgent" in text
    # And the env-var contract documented in the README.
    assert "FIREWALL_PROXY" in text


def test_bootstrap_listed_in_package_data():
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    text = pyproject.read_text()
    assert "integrations/openclaw/*.js" in text, \
        "the bootstrap JS must be glob-included in package-data so it ships in the wheel"
