---
name: finance-paper-trader
description: Place and cancel small US equity orders on an Alpaca PAPER account after checking buying power and open positions.
version: 0.1.0
license: MIT
fin_capabilities: [market_data, account_read, trade]
allow_hosts: []
allowed_tools: ["WebFetch"]
---

# finance-paper-trader

An example of a skill that legitimately moves (simulated) money. It
declares every capability it uses: quotes (`market_data`), buying power
and positions (`account_read`), and orders (`trade`). It never declares
`transfer`, so a withdrawal attempt would be MALICIOUS (invariant F1).

`firewall scan` lists `trade` as an INFO finding: a capability the
installer should see, like an app permission. With the default policy
(`finance.environment = "paper"`) the proxy denies the live host
`api.alpaca.markets` in every mode, so this skill can only reach
`paper-api.alpaca.markets` (invariant F4).

## Usage

1. `GET https://paper-api.alpaca.markets/v2/account` and check `buying_power`.
2. `GET https://paper-api.alpaca.markets/v2/positions` to avoid doubling up.
3. `POST https://paper-api.alpaca.markets/v2/orders` with a limit order.
4. `DELETE https://paper-api.alpaca.markets/v2/orders/<id>` to cancel.
