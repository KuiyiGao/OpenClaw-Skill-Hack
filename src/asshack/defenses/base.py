"""防御层抽象。

防御有两类钩子，一个防御可实现其一或兼有：
  - inspect(skill, baseline) -> list[Finding]   静态/预运行分析（检测，不阻断）
  - gate(action, skill)      -> Decision         运行时动作门控（阻断越界动作）

约定：gate/inspect **不得读取 Action.origin / AttackResult.is_malicious 等 ground-truth 字段**。
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import List, Optional

from ..skills.model import Action, Skill

_SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3}


@dataclass
class Finding:
    defense: str
    code: str
    severity: str          # info | low | medium | high
    message: str

    @property
    def rank(self) -> int:
        return _SEVERITY_ORDER.get(self.severity, 0)


@dataclass
class Decision:
    allow: bool
    reason: str = ""


class Defense(ABC):
    name: str = "abstract"

    def inspect(self, skill: Skill, baseline: Optional[Skill] = None) -> List[Finding]:
        """静态分析；默认无发现。"""
        return []

    def gate(self, action: Action, skill: Skill) -> Decision:
        """运行时门控；默认放行。"""
        return Decision(allow=True)
