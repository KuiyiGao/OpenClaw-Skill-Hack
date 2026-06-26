"""Agent Skill Firewall — runtime behavioral check for Agent Skills.

Observe, don't guess: judge a skill by what it *does* when it runs, not by
guessing from its code. See README.md for the design (L0 static gate ∪
L1 containment substrate ∪ L2 runtime Intent-Action-Result verifier) and
docs/code.pdf for the per-module commentary.

Quick start::

    pip install agent-skill-firewall
    firewall config init
    firewall start
    firewall panel
"""

__version__ = "0.1.0"

from firewall.runtime.firewall import (
    IARVerdict,
    analyze_iar,
    build_intent_envelope,
)
from firewall.skills.discover import Skill, discover_skills, load_skill
from firewall.config import Config, load_config

__all__ = [
    "__version__",
    "IARVerdict",
    "analyze_iar",
    "build_intent_envelope",
    "Skill",
    "discover_skills",
    "load_skill",
    "Config",
    "load_config",
]
