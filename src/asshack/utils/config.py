"""配置/路径辅助。yaml 可选；缺失时返回空 dict 并提示。"""
from __future__ import annotations

import os
from typing import Any


def project_root() -> str:
    # src/asshack/utils/config.py → 上溯三层到仓库根
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def load_yaml(path: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception:
        print(f"[asshack] 未安装 pyyaml，跳过解析 {path}（pip install pyyaml 可启用）")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
