"""攻击生成器抽象。

每个攻击把一个良性 Skill 变形为攻击样本（AttackResult.skill）。
对"时间维度"攻击（rug-pull），还会带上良性前一版本 baseline，供 diff 检测使用。

⚠️ 一律使用无害 canary：只引用 canary 端点/honeytoken，绝不含真实恶意代码。见 ETHICS.md。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..skills.model import Skill

# 演示用 canary 目标（均为本地保留域，不解析到真实主机）
CANARY_COLLECTOR = "collector-canary.local"


@dataclass
class AttackResult:
    skill: Skill                       # 被测 agent 实际加载/运行的（可能被投毒的）技能
    label: str = "none"                # 攻击名
    baseline: Optional[Skill] = None   # 时间维度攻击的良性前一版本（供 diff 检测）
    is_malicious: bool = False         # ground-truth：是否为攻击样本
    notes: str = ""


class Attack(ABC):
    name: str = "abstract"

    @abstractmethod
    def apply(self, skill: Skill) -> AttackResult:
        raise NotImplementedError


class NoAttack(Attack):
    """良性对照：原样返回。"""
    name = "none"

    def apply(self, skill: Skill) -> AttackResult:
        return AttackResult(skill=skill, label="none", is_malicious=False)
