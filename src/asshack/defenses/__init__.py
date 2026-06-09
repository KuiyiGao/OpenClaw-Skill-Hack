from .base import Defense, Finding, Decision
from .static_scanner import StaticScanner
from .skill_firewall import SkillFirewall
from .diff_drift import DiffDrift

REGISTRY = {
    "none": None,
    "static_scanner": StaticScanner,
    "skill_firewall": SkillFirewall,
    "diff_drift": DiffDrift,
    # "repo_triage": RepoTriage,   # TODO 立项 P2
    # "llm_judge": LlmJudge,       # TODO 立项 P2
    # "watcher": Watcher,          # TODO ClawKeeper watcher 范式
}

__all__ = [
    "Defense", "Finding", "Decision",
    "StaticScanner", "SkillFirewall", "DiffDrift", "REGISTRY",
]
