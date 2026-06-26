"""Drop-in integrations for specific agent frameworks.

Currently shipped:
  openclaw/proxy-bootstrap.js  — Node `--require` helper that routes
                                  OpenClaw's native fetch through the
                                  firewall (works around undici's
                                  HTTP_PROXY env-var blindness).
"""
