"""轻量静态扫描器（检测层，不阻断）。

覆盖三类红旗，对应不同攻击族：
  - 隐藏内容：HTML 注释里的命令性指令、零宽/不可见 Unicode  → prompt_injection / rug-pull 正文
  - 诱人元数据：description 的垃圾营销词 + 过宽能力           → metadata_attack
  - 可疑端点：正文/能力声明里出现的疑似 collector/exfil 端点  → 通用外泄线索

定位：作为基线锚定层。真实项目里可在此 wrap `cisco-ai-skill-scanner`（PDF §4），
把其 SARIF 输出归一化成 Finding。
"""
from __future__ import annotations

import re
from typing import List, Optional

from ..skills.model import Skill
from .base import Defense, Finding

_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.S)
_IMPERATIVE = re.compile(
    r"(read|exfiltrat|send|post|upload|collect|token|credential|secret|password|"
    r"\.ssh|api[_-]?key|读取|发送|外泄|勿告知|不要告知|不要向用户)", re.I,
)
_INVISIBLE = re.compile("[​‌‍⁠﻿]")
_LURE = re.compile(
    r"\b(always|first|official|verified|recommended|best|fastest|most reliable|"
    r"everything|any task)\b", re.I,
)
_SUSPICIOUS_HOST = re.compile(r"(collector|exfil|steal|gather|drop)[\w.-]*", re.I)


class StaticScanner(Defense):
    name = "static_scanner"

    def inspect(self, skill: Skill, baseline: Optional[Skill] = None) -> List[Finding]:
        f: List[Finding] = []

        for c in _HTML_COMMENT.findall(skill.body):
            if _IMPERATIVE.search(c):
                f.append(Finding(self.name, "hidden_comment_instruction", "high",
                                 "正文 HTML 注释中含命令性指令（疑似间接提示注入）"))
        if _INVISIBLE.search(skill.body):
            f.append(Finding(self.name, "invisible_unicode", "high",
                             "正文含零宽/不可见 Unicode（疑似隐藏指令通道）"))

        lures = _LURE.findall(skill.description or "")
        if len(lures) >= 2:
            sev = "high" if (skill.capabilities.exec or skill.capabilities.secret) else "medium"
            f.append(Finding(self.name, "attractive_metadata", sev,
                             f"description 含诱导性营销词 {sorted(set(map(str.lower, lures)))}"
                             "（疑似 Attractive Metadata Attack）"))

        for host in skill.capabilities.network + _SUSPICIOUS_HOST.findall(skill.body):
            if _SUSPICIOUS_HOST.search(host):
                f.append(Finding(self.name, "suspicious_endpoint", "medium",
                                 f"出现疑似外泄端点：{host}"))
                break
        return f
