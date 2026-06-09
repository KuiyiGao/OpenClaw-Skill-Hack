"""Diff-aware 版本漂移检测（对应立项 P1 / SkillRugBench）。

跨版本比对 v_n（baseline）与 v_{n+1}（当前），对**能力增量**单独建模：
  - 新增网络端点 / 文件写前缀
  - 新打开 exec / secret 能力（frontmatter 能力蔓延）
  - 正文新增混淆/隐藏内容（HTML 注释命令、不可见 Unicode）

这是 rug-pull 的对症检测：单版本快照看不出"良性 → 恶意"的转变。
没有 baseline 时本检测静默（不产生 Finding）。
"""
from __future__ import annotations

import re
from typing import List, Optional

from ..skills.model import Skill
from .base import Defense, Finding

_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.S)
_INVISIBLE = re.compile("[​‌‍⁠﻿]")


def _obfuscation_score(body: str) -> int:
    return len(_HTML_COMMENT.findall(body)) + len(_INVISIBLE.findall(body))


class DiffDrift(Defense):
    name = "diff_drift"

    def inspect(self, skill: Skill, baseline: Optional[Skill] = None) -> List[Finding]:
        if baseline is None:
            return []  # 无前一版本可比，静默
        f: List[Finding] = []
        old, new = baseline.capabilities, skill.capabilities

        new_net = [h for h in new.network if h not in old.network]
        if new_net:
            f.append(Finding(self.name, "capability_creep_network", "high",
                             f"版本 {baseline.version}→{skill.version} 新增网络端点：{new_net}"))
        new_file = [p for p in new.file if p not in old.file]
        if new_file:
            f.append(Finding(self.name, "capability_creep_file", "high",
                             f"新增文件写前缀：{new_file}"))
        if new.exec and not old.exec:
            f.append(Finding(self.name, "capability_creep_exec", "high", "新打开 exec 能力"))
        if new.secret and not old.secret:
            f.append(Finding(self.name, "capability_creep_secret", "high", "新打开 secret 能力"))

        if _obfuscation_score(skill.body) > _obfuscation_score(baseline.body):
            f.append(Finding(self.name, "new_obfuscation", "high",
                             "新版本正文新增隐藏内容/混淆（注释命令或不可见 Unicode）"))
        return f
