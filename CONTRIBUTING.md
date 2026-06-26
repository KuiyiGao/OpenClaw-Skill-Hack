# Contributing

Thanks for your interest. The package is small on purpose; contributions
are welcome as long as they keep it that way.

## Dev setup

```bash
git clone https://github.com/KuiyiGao/OpenClaw-Skill-Hack.git
cd OpenClaw-Skill-Hack
make install            # pip install -e ".[dev]"
make test               # pytest tests/unit/
make code-pdf           # rebuild docs/code.pdf (needs tectonic)
```

## Invariants and tests

The L2 verifier preserves five invariants regardless of how a user
edits `config.toml`. Each one is pinned by a single named test in
[tests/unit/test_firewall_invariants.py](tests/unit/test_firewall_invariants.py):

| # | Invariant | Test |
|---|---|---|
| 1 | Cross-plane taint | `test_cross_plane_taint_is_malicious` |
| 2 | Pre-scan defer | `test_prescan_only_critical_blocks_at_install` |
| 3 | Detection / containment separation | `test_detector_view_excludes_honeypot` |
| 4 | Unknown is not guilty | `test_unknown_destination_alone_is_not_malicious` |
| 5 | IAR 3-plane shape (no bodies) | `test_iar_egress_plane_has_no_body` |

If a change makes any of these fail, the change is wrong, not the test.

## Policy lives in TOML, not code

The runtime is policy-free. New default patterns belong in
[`firewall/config.py::DEFAULT_CONFIG_TOML`](firewall/config.py); new
regex / host / sink categories belong in `Config` dataclasses with a
matching field in the TOML template. Hard-coding patterns in
`firewall/runtime/firewall.py` is the wrong place — the user's audit
trail must remain in their TOML.

## Style

* No marketing prose in docstrings.
* No "Why this exists" preambles.
* One short line per function docstring; remove if it just restates the name.
* Comments only when the **why** is non-obvious. Section banners
  (`# --- foo ---`) get trimmed in review.

## Submitting

1. Add a test for the invariant or behaviour you're changing.
2. `make test` — all 19+ tests must pass on Python 3.10–3.12.
3. `make code-pdf` — if you touched a public source file, rebuild the
   companion document.
4. Open a PR; CI runs the same matrix.

## License

By contributing you agree your contribution is MIT-licensed.
