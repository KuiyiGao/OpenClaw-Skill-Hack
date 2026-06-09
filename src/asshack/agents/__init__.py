from .base import AgentUnderTest, Gate
from .mock import MockAgent
from .sandboxed import SandboxedAgent, SandboxSpec, NotConfigured
from .openclaw import OpenClawAgent

REGISTRY = {
    "mock": MockAgent,         # 离线脆弱 agent（攻防 harness 单测用）
    "openclaw": OpenClawAgent, # 真实 OpenClaw（在 sandbox 隔离运行，真实 LLM）
}

__all__ = [
    "AgentUnderTest", "Gate", "MockAgent",
    "SandboxedAgent", "SandboxSpec", "NotConfigured",
    "OpenClawAgent", "REGISTRY",
]
