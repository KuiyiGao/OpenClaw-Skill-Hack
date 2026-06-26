# Workflow design (research + verification)

This document records how the firewall package was built — not as
self-promotion, but because the workflow shape is a useful pattern for
anyone designing a similar small, audit-heavy package.

## The shape

The package was authored in three phases, each driven by a small fan-out
of independent agents whose results were then synthesised by hand:

1. **Research phase** — five parallel agents over the source repo and
   the public web:
   * inventory + personal-info audit;
   * heuristic compression map (every regex / pattern in the old
     codebase, judged keep / simplify / parameterize-via-config /
     remove);
   * Agent Skill format survey across frameworks (Anthropic SDK, Claude
     Code, OpenClaw, Cursor, OpenCode);
   * TUI + CLI pattern survey (Rich vs Textual, XDG config layout);
   * verbatim extraction of the research numbers used in the README.

2. **Build phase** — single-author. The implementation was sequential
   because every file needed to fit a coherent design. The phase-1
   research is the reason every file knows its place.

3. **Verification phase** — four parallel agents independently:
   * fresh-clone the public remote, install, run tests;
   * walk the 8-point requirements checklist;
   * recompile `docs/code.pdf` and confirm every source file has a
     documented section;
   * adversarially attempt 8 distinct config-only jailbreaks against
     the five L2 invariants.

The verification's jailbreak pass found one real bug — a wildcard
`refusal_patterns` could downgrade the SUSPICIOUS tier to BENIGN —
which is fixed in the source and pinned by
`tests/unit/test_firewall_invariants.py::test_refusal_pattern_cannot_downgrade_suspicious`.

## Why it matters for the package

Two lessons baked into the source:

* **One named invariant, one named test.** Every promise the firewall
  makes about what it will detect lives both in the L2 module docstring
  and in a test whose name is the invariant. A future contributor who
  refactors `analyze_iar` will know exactly which line they broke.
* **Audits that aren't on disk don't exist.** The verification phase
  uses fresh clones, not the working tree, so a contributor can repeat
  it cold. `make code-pdf` and `make test` are the two commands that
  matter; both are deliberately one-liner.
