"""asshack — Agent Skill Security 攻防研究框架（防御性/测量性）。

子包：
  skills/    技能数据模型 + 加载器
  agents/    被测智能体（Agent-Under-Test）抽象 + Mock
  attacks/   攻击生成器（注入 / 元数据 / rug-pull）
  defenses/  防御层（静态扫描 / skill firewall / diff-drift）
  harness/   评测编排 + 指标 + canary 记账

仅用于防御研究；攻击载荷一律为无害 canary，见 ETHICS.md。
"""

__version__ = "0.1.0"
