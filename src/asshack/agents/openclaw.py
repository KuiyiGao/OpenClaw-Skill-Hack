"""OpenClaw 适配器（真实 npm 包 openclaw）。

实测已跑通：OpenClaw 2026.6.1 在隔离容器内用【真实 LLM】运行（key 来自 sandbox/.env）。
主要操作入口是 sandbox 脚本（更直观、可监控）：
  - 启停：       make oc-up / oc-down
  - 提问/观察：  make oc-ask MSG="..."   + ./sandbox/monitor.sh
  - 技能门控：   ./sandbox/skillctl.sh add <dir>（Cisco 扫描门 + 你批准）

本适配器为 Python 侧的【预留接口】，便于把 OpenClaw 接入 harness 做批量评测；
具体一次性命令见 SandboxSpec.run_cmd（model=real/<env LLM_MODEL>）。
"""
from __future__ import annotations

from .sandboxed import SandboxedAgent, SandboxSpec


class OpenClawAgent(SandboxedAgent):
    name = "openclaw"
    spec = SandboxSpec(
        image="asshack-openclaw:latest",
        skills_dir="/home/lab/.openclaw/workspace/skills",
        run_cmd=["bash", "-lc",
                 "openclaw agent --local --model real/$LLM_MODEL "
                 "--session-key agent:lab:1 --message '{task}' --json"],
        required_env=["LLM_API_KEY"],   # 真实模型凭据，来自 sandbox/.env
        profile="",                      # 新 compose 无 profile，默认即 OpenClaw lab
        compose_file="sandbox/docker-compose.yml",
    )
