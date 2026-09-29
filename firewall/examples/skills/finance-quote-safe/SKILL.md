---
name: finance-quote-safe
description: Fetch the latest quote and recent daily bars for a US stock symbol from Alpaca market data. Read-only; never touches the trading account.
version: 0.1.0
license: MIT
fin_capabilities: [market_data]
allow_hosts: []
allowed_tools: ["WebFetch"]
---

# finance-quote-safe

A minimal financial skill that does exactly what its manifest declares:
it reads public market data and nothing else.

**Declared capability: `market_data`.** Under the firewall, requests to
`data.alpaca.markets` are in intent. Any request that reads the account
(`account_read`) is a divergence, and any request that places or cancels an
order (`trade`) is a MALICIOUS confirmation, because the manifest never
asked for it (invariant F1).

## Usage

When asked for a quote, call
`GET https://data.alpaca.markets/v2/stocks/<SYMBOL>/quotes/latest`
and summarise bid, ask and spread in one line. For recent history, call
`GET https://data.alpaca.markets/v2/stocks/<SYMBOL>/bars?timeframe=1Day&limit=5`.
