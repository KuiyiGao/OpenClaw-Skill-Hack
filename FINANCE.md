# Financial agents

The base firewall asks *where did the bytes go?* For a financial agent the
sharper question is *what did the skill do with money?* A request to your
broker is normal traffic; the attack is a "quote lookup" skill that places an
order, reads your positions and ships them elsewhere, or withdraws funds.

The financial plane answers that question with the same Intent-Action-Result
(IAR) shape as the rest of the L2 verifier: the skill declares a capability,
the firewall classifies what it actually did, and divergence is scored.

## Try it

```bash
export DEEPSEEK_API_KEY=...          # `firewall start` requires the driver key
firewall start                       # terminal 1: proxy + canary, balanced + paper

# terminal 2
P=http://127.0.0.1:8080
curl -s -o /dev/null -w "%{http_connect}\n" -x $P https://api.alpaca.markets/v2/account
#   403: live trading host while finance.environment = paper (F4)
curl -s -x $P -X POST -d '{}' http://paper-api.alpaca.markets/v2/orders
#   {"firewall":"captured"}: paper-api is not in allow_hosts, so the order never left

firewall watch firewall/examples/skills/finance-quote-safe \
  --log-file "<events_path from: firewall config show>"
#   MALICIOUS  confirmations: fin_undeclared:trade@paper-api.alpaca.markets, ...
```

To let a paper-trading agent actually reach its broker, add the hosts it
needs (e.g. `paper-api.alpaca.markets`, `data.alpaca.markets`) to
`[egress].allow_hosts`. Existing config files keep working without a
`[finance]` section: the defaults apply. `watch` replays the whole file you
give it, so slice one run's events into its own log for a per-run verdict.

## Capability model

| Capability | Covers | Moves money |
|---|---|---|
| `market_data` | quotes, bars, reference data | no |
| `account_read` | balances, positions, order history | no |
| `trade` | place / replace / cancel orders, close positions | yes |
| `transfer` | withdrawals and wires out of the account | yes |

A skill declares what it uses in its SKILL.md frontmatter (top level, or
under `metadata:` for spec-strict agents):

```yaml
---
name: finance-quote-safe
description: Fetch the latest quote for a US stock symbol.
fin_capabilities: [market_data]
---
```

The user's policy caps what any skill may use:

```toml
[finance]
environment = "paper"                                       # or "live"
allowed_capabilities = ["market_data", "account_read", "trade"]
```

**Effective capabilities = declared ∩ allowed.** Declarations are
self-asserted by the skill author, so they are shown to the installer
(`firewall skills`, `firewall scan`) like app permissions; the policy ceiling
is what holds even against a skill that declares everything. Declarations are
a set, not a ladder: declaring `transfer` does not grant `trade`.

## Invariants

Pinned by one named test each in
[tests/unit/test_finance_invariants.py](tests/unit/test_finance_invariants.py).

| # | Invariant | Test |
|---|---|---|
| F1 | Money movement is never implicit: an exactly classified `trade`/`transfer` outside the effective capabilities is MALICIOUS | `test_undeclared_money_movement_is_malicious` |
| F2 | Ambiguity is not guilt: a host-level classification is at most SUSPICIOUS unless another plane confirms | `test_host_level_financial_ambiguity_is_not_guilt` |
| F3 | Account data is a taint source: exact account access plus an out-of-policy send is MALICIOUS (extends invariant 1) | `test_account_data_plus_oop_send_is_malicious` |
| F4 | Paper means paper: with `environment = "paper"` the proxy denies `live_hosts` in every policy mode, observe included | `test_paper_mode_denies_live_hosts_even_in_observe` |

**Detection vs prevention.** F1–F3 are verdicts computed from a run's
evidence: by the time a run is judged MALICIOUS its order may already have
been sent. The only financial control that acts *before* a request leaves
today is F4 at the proxy. Pre-trade prevention is M2 on the roadmap.

Design choices worth knowing:

* **F4 overrides `observe`.** Observe mode exists to learn which hosts an
  agent needs; it must never be the reason a real-money order goes out.
  Any `environment` value other than `"live"` counts as paper (fail closed).
* **F4 matches hostnames.** A skill that deliberately reaches a broker by IP
  literal or a DNS alias is not a `live_hosts` match. `balanced` and `strict`
  still deny it, because an unknown CONNECT host is refused; `observe` lets
  unknown hosts through, so it does not. The dependable control is key
  hygiene: in paper mode, give the agent paper keys only (M3 goes further and
  keeps keys away from skills entirely).
* **A broker the skill declared a use for is not an exfiltration target.**
  A read-only portfolio skill talking to its own broker never triggers F3.
  A catalog host the skill has *no* declared use for is still an
  out-of-policy send, so invariant 1 keeps working.

## Visibility: host-level vs route-level

Brokers speak HTTPS. Through a plain forward proxy the firewall sees only
`CONNECT paper-api.alpaca.markets:443`: it knows the host, not whether the
request read the account or placed an order. The catalog therefore has two
kinds of rules:

* **host-level** (no `method`/`path`): the most a request to that host could
  do. It is the only kind a CONNECT can match, and it is never enough for a
  MALICIOUS verdict on its own (F2).
* **route-level** (`method` and/or `path`): an exact classification, used
  when the route is visible: plain HTTP through the proxy, or a tool call.

Tool calls are always route-level: `mcp__alpaca__place_stock_order` says what
it does. See the roadmap for how the firewall gets route-level visibility of
HTTPS without intercepting TLS.

## The catalog

`[finance].endpoints` maps requests to capabilities; `tool_capabilities`
maps tool names (case-insensitive regex) to capabilities. The shipped
entries (Alpaca, Binance spot) are **reference entries**: verify them
against the broker's current API docs before relying on them. Live hosts
assume the worst (`transfer`) until you have checked their API surface.

Matching rules: the most specific rule wins (longest path pattern, then a
rule naming the method), ties go to the higher capability, paths match
case-insensitively without the query string, and a catalog host with no
matching rule falls back to the highest capability it serves.
`firewall doctor` reports entries that can never match: unknown capability
names, a rule without a host or pattern, a regex that does not compile.

### Adding a broker

1. Read the broker's API reference and list its hosts: which serve market
   data only, which serve the account, which are paper vs live.
2. Add one host-level rule per host (its worst case), then route-level rules
   for each endpoint family, in `[finance].endpoints`.
3. Add live trading hosts to `live_hosts`.
4. Check each rule: `firewall finance classify <host> <METHOD> <path>`
   (omit METHOD/path to see what a CONNECT maps to), and
   `firewall finance classify --tool <name>` for its MCP tool names.
5. Add a parametrized case to `test_catalog_most_specific_rule_wins` if you
   change the shipped defaults, and keep `DEFAULT_CONFIG_TOML` and
   `FinanceConfig` identical (`test_finance_template_matches_dataclass_defaults`).

## Roadmap

| Milestone | Scope | Status |
|---|---|---|
| M1 | Capability model, catalog, F1-F4, paper-mode proxy guard, JSONL replay fix | done |
| M2 | Tool-call ingestion: agent hooks (Claude Code `PreToolUse`, OpenClaw) append `tool` events; a pre-trade guard answers allow/deny *before* an order tool runs, with limits (max notional, symbol allowlist, orders per run) | next |
| M3 | Keyless skills: a broker gateway on the firewall holds the API keys, the skill calls it over plain HTTP, and the gateway classifies the exact route, enforces capabilities and limits, injects the key and forwards over TLS. Route-level visibility without a MITM CA, and nothing for a skill to exfiltrate | design |
| M4 | Tamper-evident audit trail: hash-chained `events.jsonl` and `firewall audit verify` | planned |
| M5 | Evaluation: a labelled corpus of financial-skill traces (synthetic evidence, no live malware) and precision/recall in `firewall bench` | planned |

## Known gaps in the base firewall

Found while building M1; each is a small, self-contained change.

* `DEFAULT_CONFIG_TOML` has drifted from the dataclass defaults in `[judge]`
  and `[taint]`: a user who runs `firewall config init` gets fewer secret
  patterns (no `.npmrc`, `.netrc`, `.config/gh`) than the tests exercise.
  A drift test like the finance one would pin it.
* `[secrets].secret_paths` and `secret_env` are displayed by
  `firewall config show` but never used by detection.
* Live proxy logs carry no tool calls yet, so the tool plane is fed only by
  callers of `analyze_iar` until M2.
* `firewall doctor` counts the docker and tectonic checks as required: their
  labels read `(optional, for ...)`, but the gate looks for the literal
  `(optional)`, so a machine without them exits 1.
