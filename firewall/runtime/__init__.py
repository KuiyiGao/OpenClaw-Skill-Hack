"""Runtime (L2) layer of the firewall.

The L2 verifier runs after a skill is admitted under watch by L0/L1.
It scores the skill's runtime actions against its declared intent and
returns an IAR verdict. See ``firewall.runtime.firewall`` for the core.
"""
