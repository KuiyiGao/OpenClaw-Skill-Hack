from __future__ import annotations


def decide(phase, host, method, body):
    # Reserved firewall extension hook. Return "deny" or "capture" to override the default egress
    # decision, or None to fall back to the built-in allowlist + honeypot. It can only make egress
    # stricter, never widen it. phase is "connect" (HTTPS) or "http" (plain HTTP); body is the
    # request body for "http", else None. Example DLP rule (uncomment to use):
    #   if phase == "http" and body and "BEGIN PRIVATE KEY" in body: return "deny"
    return None
