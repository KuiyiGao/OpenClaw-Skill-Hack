"""Skill Firewall：intent–action 一致性执行层门控（对应立项 P4）。

把 frontmatter 声明的能力当作允许边界，在动作执行前拦截"声明外"的动作：
  - network：目标端点必须在 capabilities.network 白名单内
  - file   ：写入路径必须落在 capabilities.file 的某个前缀下
  - exec   ：仅当 capabilities.exec 为真
  - read_secret：仅当 capabilities.secret 为真

这正是 Attractive Metadata Attack（2508.02110）呼吁的"执行层防御"，
也是把 17% 抬高的轻量替代/补充。

⚠️ 已知边界（演示要点）：纯声明式门控对 **rug-pull** 无效——攻击者会顺手蔓延 manifest，
使越界动作"在声明之内"。因此 firewall 必须与 diff_drift（跨版本能力增量）叠加。
gate() 严禁读取 Action.origin 等 ground-truth 字段，仅依据声明与动作本身判定。
"""
from __future__ import annotations

from ..skills.model import Action, Skill
from .base import Decision, Defense


class SkillFirewall(Defense):
    name = "skill_firewall"

    def gate(self, action: Action, skill: Skill) -> Decision:
        caps = skill.capabilities
        if action.kind == "reply":
            return Decision(True)

        if action.kind == "network":
            if action.target in caps.network:
                return Decision(True)
            return Decision(False, f"端点 {action.target} 不在声明白名单 {caps.network}")

        if action.kind == "file":
            if any(action.target.startswith(p) for p in caps.file):
                return Decision(True)
            return Decision(False, f"文件 {action.target} 不在声明前缀 {caps.file}")

        if action.kind == "exec":
            return Decision(caps.exec, "" if caps.exec else "技能未声明 exec 能力")

        if action.kind == "read_secret":
            return Decision(caps.secret, "" if caps.secret else "技能未声明 secret 能力")

        return Decision(False, f"未知动作类型 {action.kind}（默认拒绝）")
