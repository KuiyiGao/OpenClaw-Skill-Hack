"""被测智能体（Agent-Under-Test, AUT）抽象。

任何 agent（OpenClaw 等）只要实现
`run(task, skill, gate)`，即可接入评测。`gate` 是运行时防御（如 skill firewall）
注入的动作门控：在每个动作"执行"前被调用，返回是否放行。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from ..skills.model import Action, AgentRun, Skill

# 运行时门控：给定 (action, skill) 返回 (allow, reason)
Gate = Callable[[Action, Skill], "tuple[bool, str]"]


def allow_all(action: Action, skill: Skill) -> "tuple[bool, str]":
    return True, ""


class AgentUnderTest(ABC):
    """所有被测智能体的统一接口。"""

    name: str = "abstract"

    @abstractmethod
    def run(self, task: str, skill: Skill, gate: Optional[Gate] = None) -> AgentRun:
        """在加载了 `skill` 的情况下执行 `task`，返回运行结果。

        实现约定：
          - 对每个打算执行的动作，先调用 gate(action, skill)；为 False 则计入
            run.blocked 而非 run.actions。
          - completed_task：真实用户任务是否完成（效用）。
          - followed_injection：是否执行了隐藏/越界动作（攻击成功）。
        """
        raise NotImplementedError
