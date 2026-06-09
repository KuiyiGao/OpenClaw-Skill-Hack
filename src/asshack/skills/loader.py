"""SKILL.md 加载器：拆分 frontmatter / 正文，解析为 Skill。

优先用 pyyaml；缺失时回退到一个仅覆盖本项目 frontmatter 子集的极简解析器，
以保证 scripts/run_demo.py 在零依赖下也能运行。
"""
from __future__ import annotations

import os
from typing import Tuple

from .model import Skill, Capabilities

try:  # pragma: no cover - 取决于环境
    import yaml  # type: ignore

    def _yaml_load(s: str) -> dict:
        return yaml.safe_load(s) or {}
except Exception:  # pyyaml 不可用 → 极简解析器
    def _yaml_load(s: str) -> dict:
        return parse_frontmatter(s)


# --------------------------------------------------------------------------- #
# 极简 YAML 子集解析器（仅支持本项目用到的：标量 / 一层嵌套 map / 流式列表）
# --------------------------------------------------------------------------- #
def _split_flow(inner: str) -> list[str]:
    out, buf, q = [], [], None
    for ch in inner:
        if q:
            buf.append(ch)
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            buf.append(ch)
        elif ch == ",":
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf))
    return [x.strip() for x in out if x.strip()]


def _scalar(s: str):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_scalar(x) for x in _split_flow(inner)] if inner else []
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~", ""):
        return None
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            pass
    return s


def parse_frontmatter(text: str) -> dict:
    lines = text.splitlines()
    result: dict = {}
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent != 0:  # 顶层意外缩进，跳过
            i += 1
            continue
        key, _, val = raw.strip().partition(":")
        key, val = key.strip(), val.strip()
        if val == "":  # 可能是嵌套块
            block: dict = {}
            j = i + 1
            while j < n:
                child = lines[j]
                if not child.strip() or child.lstrip().startswith("#"):
                    j += 1
                    continue
                if (len(child) - len(child.lstrip())) == 0:
                    break
                ck, _, cv = child.strip().partition(":")
                block[ck.strip()] = _scalar(cv.strip())
                j += 1
            result[key] = block if block else None
            i = j
        else:
            result[key] = _scalar(val)
            i += 1
    return result


# --------------------------------------------------------------------------- #
def split_frontmatter(text: str) -> Tuple[str, str]:
    """返回 (frontmatter_text, body)。允许 frontmatter 前有注释/空行。"""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip() == "---"), None)
    if start is None:
        return "", text
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return "", text
    return "\n".join(lines[start + 1:end]), "\n".join(lines[end + 1:])


def load_skill(path: str) -> Skill:
    """从目录（含 SKILL.md）或直接的 SKILL.md 文件加载技能。"""
    if os.path.isdir(path):
        skill_md = os.path.join(path, "SKILL.md")
        scripts = {
            fn: open(os.path.join(path, fn), "r", encoding="utf-8", errors="replace").read()
            for fn in os.listdir(path)
            if fn != "SKILL.md" and os.path.isfile(os.path.join(path, fn))
        }
    else:
        skill_md, scripts = path, {}

    with open(skill_md, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    fm_text, body = split_frontmatter(text)
    fm = _yaml_load(fm_text) if fm_text else {}

    return Skill(
        name=str(fm.get("name", os.path.basename(os.path.dirname(skill_md)) or "unnamed")),
        version=str(fm.get("version", "0.0.0")),
        description=str(fm.get("description", "")),
        body=body,
        capabilities=Capabilities.from_dict(fm.get("capabilities")),
        frontmatter=fm,
        scripts=scripts,
        source_path=path,
    )
