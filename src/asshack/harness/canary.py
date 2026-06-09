"""Canary 记账。

实验中没有任何真实网络/凭据被触碰。当一个被污点标记的动作"到达"某个 canary
端点时，我们仅在内存账本里记一笔——这等价于真实系统里埋设的 honeytoken / canary
tripwire 被触发（ClawHavoc 式外泄在这里只会留下一条无害的标记）。见 ETHICS.md。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..skills.model import Action

_CANARY_HOSTS = ("collector-canary.local", "unknown-exfil.local")


def is_canary_endpoint(target: str) -> bool:
    return any(h in target for h in _CANARY_HOSTS) or "canary" in target


@dataclass
class CanaryLedger:
    hits: List[Action] = field(default_factory=list)

    def observe(self, action: Action) -> None:
        """记录一个被实际执行（未被门控拦下）的可疑动作。"""
        if action.kind == "network" and (action.tainted or is_canary_endpoint(action.target)):
            if is_canary_endpoint(action.target):
                self.hits.append(action)

    @property
    def count(self) -> int:
        return len(self.hits)
