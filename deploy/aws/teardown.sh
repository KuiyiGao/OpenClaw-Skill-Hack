#!/usr/bin/env bash
# 用完即焚：按 .lab-state.env 精确销毁 launch.sh 创建的 EC2 资源。
# 即使不跑这个，实例也会在 power_state 定时关机 + shutdown-behavior=terminate 后自动终止(双保险)。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
STATE="$HERE/.lab-state.env"
[ -f "$STATE" ] || { echo "找不到 $STATE，无可清理(或已清理)。"; exit 0; }
# shellcheck disable=SC1090
source "$STATE"

command -v aws >/dev/null || { echo "需要 aws CLI"; exit 1; }
R="$AWS_REGION"

echo "==> 终止实例 $INSTANCE_ID ..."
aws ec2 terminate-instances --region "$R" --instance-ids "$INSTANCE_ID" >/dev/null 2>&1 || true
aws ec2 wait instance-terminated --region "$R" --instance-ids "$INSTANCE_ID" 2>/dev/null || true

echo "==> 删除安全组 $SECURITY_GROUP_ID ..."
aws ec2 delete-security-group --region "$R" --group-id "$SECURITY_GROUP_ID" >/dev/null 2>&1 || true

echo "==> 删除密钥对 $KEY_PAIR_NAME ..."
aws ec2 delete-key-pair --region "$R" --key-name "$KEY_PAIR_NAME" >/dev/null 2>&1 || true
[ -n "${KEY_FILE:-}" ] && rm -f "$KEY_FILE"

rm -f "$STATE"
echo "[✓] 已清理完毕。"
