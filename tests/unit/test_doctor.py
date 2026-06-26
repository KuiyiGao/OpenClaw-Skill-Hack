"""Regression tests for ``firewall doctor``.

Asserts:
  * port checks are OPTIONAL — a bound proxy port must not flip exit to 1
  * the required-failure predicate ignores any label containing "(optional)"
"""

from __future__ import annotations

import re

from firewall import cli as cli_mod


def test_port_check_labels_are_marked_optional():
    """The doctor source must mark port checks ``(optional)`` so a bound
    port does not push exit status to 1.
    """
    src = cli_mod.__file__
    text = open(src, encoding="utf-8").read()
    # both port-check labels must include the literal ``(optional)`` substring
    assert re.search(r'"proxy port \d+ \(optional\)"', text), \
        "proxy port check must be labelled (optional)"
    assert re.search(r'"canary port \d+ \(optional\)"', text), \
        "canary port check must be labelled (optional)"


def test_required_failure_gate_uses_parenthesised_optional():
    """The predicate must look for ``(optional)`` — not the bare word
    ``optional`` — so it doesn't accidentally let through a check whose
    text happens to mention "optional" in prose.
    """
    src = open(cli_mod.__file__, encoding="utf-8").read()
    assert '"(optional)" not in label' in src, \
        "doctor must gate required-failures on the parenthesised substring"
