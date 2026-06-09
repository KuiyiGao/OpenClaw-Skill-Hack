"""技能与运行时动作的数据模型。"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Capabilities:
    """技能在 frontmatter 中"声明"的能力（白名单）。

    防御侧（skill firewall）以此作为允许动作的边界；
    攻击侧（rug-pull）则可能"蔓延"这些声明以骗过纯声明式门控。
    """
    network: list[str] = field(default_factory=list)  # 允许访问的端点/主机
    file: list[str] = field(default_factory=list)      # 允许写入的文件路径前缀
    exec: bool = False                                 # 是否允许执行子进程
    secret: bool = False                               # 是否需要读取凭据/密钥

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Capabilities":
        d = d or {}
        def _as_list(v):
            if v is None:
                return []
            return list(v) if isinstance(v, (list, tuple)) else [v]
        return cls(
            network=_as_list(d.get("network")),
            file=_as_list(d.get("file")),
            exec=bool(d.get("exec", False)),
            secret=bool(d.get("secret", False)),
        )


@dataclass
class Skill:
    """一个 Agent Skill：SKILL.md 的 frontmatter + 正文 + 可选捆绑脚本。"""
    name: str
    version: str
    description: str
    body: str
    capabilities: Capabilities = field(default_factory=Capabilities)
    frontmatter: dict = field(default_factory=dict)
    scripts: dict = field(default_factory=dict)   # filename -> content
    source_path: Optional[str] = None

    def clone(self) -> "Skill":
        """深拷贝，供攻击生成器在不破坏原件的前提下变形。"""
        return copy.deepcopy(self)


@dataclass
class Action:
    """智能体在运行技能过程中采取的一个运行时动作。

    `origin` 是 ground-truth 标签，仅供 harness 计算指标使用，
    **防御组件不得读取它**（否则等于偷看答案）。
    """
    kind: str                      # network | file | exec | read_secret | reply
    target: str = ""               # 端点 / 路径 / 命令
    detail: str = ""
    tainted: bool = False          # 是否携带敏感数据（污点）
    origin: str = "visible"        # ground-truth: visible | hidden | declared


@dataclass
class AgentRun:
    """一次被测智能体运行的结果。"""
    actions: list[Action] = field(default_factory=list)        # 实际执行（通过门控）的动作
    blocked: list[Action] = field(default_factory=list)        # 被防御门控拦下的动作
    final_output: str = ""
    completed_task: bool = False    # 是否完成真实用户任务（效用）
    followed_injection: bool = False  # 是否执行了隐藏/越界动作（攻击成功）
    refused: bool = False
