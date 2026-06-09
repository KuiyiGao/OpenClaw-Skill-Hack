#!/usr/bin/env bash
# 用完即焚：按 .lab-state.env 精确销毁 launch.sh 创建的全部资源。
# 即使你没跑这个，实例也会在 AutoReleaseTime 自动释放(双保险)。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
STATE="$HERE/.lab-state.env"
[ -f "$STATE" ] || { echo "找不到 $STATE，无可清理(或已清理)。"; exit 0; }
# shellcheck disable=SC1090
source "$STATE"

command -v aliyun >/dev/null || { echo "需要 aliyun CLI"; exit 1; }
ali() { aliyun ecs "$@" --RegionId "$REGION"; }
wait_gone() {  # 等实例彻底消失，否则 SG 删不掉
  for _ in $(seq 1 40); do
    n="$(ali DescribeInstances --InstanceIds "['$INSTANCE_ID']" | \
         jq -r '.Instances.Instance | length' 2>/dev/null || echo 0)"
    [ "$n" = "0" ] && return 0; sleep 5
  done
}

echo "==> 释放实例 $INSTANCE_ID ..."
ali DeleteInstance --InstanceId "$INSTANCE_ID" --Force true >/dev/null 2>&1 || true
wait_gone

echo "==> 删除安全组 $SECURITY_GROUP_ID ..."
ali DeleteSecurityGroup --SecurityGroupId "$SECURITY_GROUP_ID" >/dev/null 2>&1 || true

echo "==> 删除密钥对 $KEY_PAIR_NAME ..."
ali DeleteKeyPairs --KeyPairNames "['$KEY_PAIR_NAME']" >/dev/null 2>&1 || true
[ -n "${KEY_FILE:-}" ] && rm -f "$KEY_FILE"

# 仅删除我们【自己创建】的网络资源；复用的默认 VPC/vSwitch 保留
if [ -n "${CREATED_VSWITCH_ID:-}" ]; then
  echo "==> 删除临时 vSwitch $CREATED_VSWITCH_ID ..."
  for _ in $(seq 1 20); do
    ali DeleteVSwitch --VSwitchId "$CREATED_VSWITCH_ID" >/dev/null 2>&1 && break; sleep 5
  done
fi
if [ -n "${CREATED_VPC_ID:-}" ]; then
  echo "==> 删除临时 VPC $CREATED_VPC_ID ..."
  for _ in $(seq 1 20); do
    ali DeleteVpc --VpcId "$CREATED_VPC_ID" >/dev/null 2>&1 && break; sleep 5
  done
fi

rm -f "$STATE"
echo "[✓] 已清理完毕。"
