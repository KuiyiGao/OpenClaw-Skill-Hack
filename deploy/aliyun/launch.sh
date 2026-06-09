#!/usr/bin/env bash
# 一键起一台【一次性】阿里云 ECS 隔离实验 VM(AWS launch.sh 的阿里云同款)。
#
# 预算护栏：
#   - AutoReleaseTime：实例在 ALI_TTL_HOURS 小时后【自动释放】(默认 8h)——忘了销毁也不会一直计费。
#   - PostPaid 按量 + PayByTraffic 按流量；最小机型；公网带宽默认 5Mbps。
#   - 所有新建资源 ID 落盘到 .lab-state.env，teardown.sh 据此精确清理。
#
# 用法：
#   aliyun configure                       # 先配置好 AccessKey/Secret
#   export ALI_REGION=cn-hangzhou
#   ./deploy/aliyun/launch.sh
#   ...实验...
#   ./deploy/aliyun/teardown.sh            # 用完即焚
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
STATE="$HERE/.lab-state.env"

REGION="${ALI_REGION:-cn-hangzhou}"
NAME="${ALI_NAME:-asshack-lab}"
TYPE="${ALI_INSTANCE_TYPE:-ecs.e-c1m2.large}"   # 2vCPU/4GB,够跑框架
TTL_HOURS="${ALI_TTL_HOURS:-8}"
BANDWIDTH="${ALI_BANDWIDTH:-5}"

# --- 依赖检查 ---
command -v aliyun >/dev/null || { echo "需要 aliyun CLI(https://help.aliyun.com/zh/cli/)"; exit 1; }
command -v jq     >/dev/null || { echo "需要 jq(brew install jq)"; exit 1; }
command -v curl   >/dev/null || { echo "需要 curl"; exit 1; }

[ -f "$STATE" ] && { echo "已存在 $STATE，疑似有未清理的实验。请先 ./deploy/aliyun/teardown.sh"; exit 1; }

ali() { aliyun ecs "$@" --RegionId "$REGION"; }

iso_in_hours() {  # 跨平台(GNU/BSD date)生成 UTC ISO8601
  local h="$1"
  date -u -d "+$h hours" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || date -u -v+"${h}"H +%Y-%m-%dT%H:%M:%SZ
}

echo "==> region=$REGION  type=$TYPE  auto-release=+${TTL_HOURS}h"
MYIP="$(curl -s https://checkip.amazonaws.com)"
echo "==> 你的公网 IP=$MYIP(安全组将只放行该 IP 的 22 端口)"

# --- 1) 网络：优先复用已有 VPC/vSwitch，没有就创建并记录 ---
CREATED_VPC=""; CREATED_VSW=""
VPC_ID="${ALI_VPC_ID:-$(ali DescribeVpcs --PageSize 50 | jq -r '.Vpcs.Vpc[0].VpcId // empty')}"
if [ -z "$VPC_ID" ]; then
  echo "==> 无可用 VPC，创建临时 VPC..."
  VPC_ID="$(ali CreateVpc --CidrBlock 192.168.0.0/16 | jq -r '.VpcId')"
  CREATED_VPC="$VPC_ID"
  for _ in $(seq 1 30); do
    st="$(ali DescribeVpcs --VpcId "$VPC_ID" | jq -r '.Vpcs.Vpc[0].Status // empty')"
    [ "$st" = "Available" ] && break; sleep 3
  done
fi
VSW_ID="${ALI_VSWITCH_ID:-$(ali DescribeVSwitches --VpcId "$VPC_ID" --PageSize 50 | jq -r '.VSwitches.VSwitch[0].VSwitchId // empty')}"
if [ -z "$VSW_ID" ]; then
  ZONE="${ALI_ZONE:-$(ali DescribeZones | jq -r '.Zones.Zone[0].ZoneId')}"
  echo "==> 无 vSwitch，在 $ZONE 创建临时 vSwitch..."
  VSW_ID="$(ali CreateVSwitch --VpcId "$VPC_ID" --CidrBlock 192.168.0.0/24 --ZoneId "$ZONE" | jq -r '.VSwitchId')"
  CREATED_VSW="$VSW_ID"
  for _ in $(seq 1 30); do
    st="$(ali DescribeVSwitches --VSwitchId "$VSW_ID" | jq -r '.VSwitches.VSwitch[0].Status // empty')"
    [ "$st" = "Available" ] && break; sleep 3
  done
fi
echo "==> VPC=$VPC_ID  vSwitch=$VSW_ID"

# --- 2) 安全组：只放行你的 IP SSH(22) ---
SG_ID="$(ali CreateSecurityGroup --VpcId "$VPC_ID" --SecurityGroupName "$NAME-sg" \
        --Description 'asshack disposable lab' | jq -r '.SecurityGroupId')"
ali AuthorizeSecurityGroup --SecurityGroupId "$SG_ID" \
    --IpProtocol tcp --PortRange 22/22 --SourceCidrIp "${MYIP}/32" --Policy accept >/dev/null
echo "==> SecurityGroup=$SG_ID(仅 ${MYIP}/32 可 SSH)"

# --- 3) 临时密钥对 ---
KEY_FILE="$HERE/$NAME-key.pem"
ali CreateKeyPair --KeyPairName "$NAME-key" | jq -r '.PrivateKeyBody' > "$KEY_FILE"
chmod 600 "$KEY_FILE"
echo "==> KeyPair=$NAME-key  ->  $KEY_FILE"

# --- 4) 镜像：最新 Ubuntu 22.04 系统镜像(可用 ALI_IMAGE_ID 覆盖) ---
IMAGE_ID="${ALI_IMAGE_ID:-$(ali DescribeImages --OSType linux --ImageOwnerAlias system \
  --PageSize 100 | jq -r '[.Images.Image[]|select(.OSName|test("Ubuntu.*22.04"))]
  | sort_by(.CreationTime) | last | .ImageId // empty')}"
[ -n "$IMAGE_ID" ] || { echo "未找到 Ubuntu 22.04 镜像，请用 ALI_IMAGE_ID 指定"; exit 1; }
echo "==> Image=$IMAGE_ID"

# --- 5) 起实例(cloud-init 作 UserData；AutoReleaseTime 作预算护栏) ---
UD_B64="$(base64 < "$ROOT/deploy/cloud-init.yaml" | tr -d '\n')"
RELEASE="$(iso_in_hours "$TTL_HOURS")"
IID="$(ali RunInstances \
  --ImageId "$IMAGE_ID" --InstanceType "$TYPE" \
  --SecurityGroupId "$SG_ID" --VSwitchId "$VSW_ID" --KeyPairName "$NAME-key" \
  --InternetChargeType PayByTraffic --InternetMaxBandwidthOut "$BANDWIDTH" \
  --InstanceChargeType PostPaid --SpotStrategy NoSpot --Amount 1 \
  --UserData "$UD_B64" --InstanceName "$NAME" --HostName "$NAME" \
  --AutoReleaseTime "$RELEASE" \
  --Tag.1.Key purpose --Tag.1.Value disposable-security-research \
  | jq -r '.InstanceIdSets.InstanceIdSet[0]')"
echo "==> Instance=$IID(将于 $RELEASE 自动释放)"

# --- 6) 落盘状态(供 teardown 精确清理) ---
cat > "$STATE" <<EOF
REGION=$REGION
INSTANCE_ID=$IID
SECURITY_GROUP_ID=$SG_ID
KEY_PAIR_NAME=$NAME-key
KEY_FILE=$KEY_FILE
CREATED_VPC_ID=$CREATED_VPC
CREATED_VSWITCH_ID=$CREATED_VSW
AUTO_RELEASE=$RELEASE
EOF

# --- 7) 等 Running + 取公网 IP ---
echo -n "==> 等待 Running"
IP=""
for _ in $(seq 1 40); do
  info="$(ali DescribeInstances --InstanceIds "['$IID']")"
  st="$(echo "$info" | jq -r '.Instances.Instance[0].Status // empty')"
  IP="$(echo "$info" | jq -r '.Instances.Instance[0].PublicIpAddress.IpAddress[0] // empty')"
  [ "$st" = "Running" ] && [ -n "$IP" ] && break
  echo -n "."; sleep 5
done
echo ""
echo "PUBLIC_IP=$IP" >> "$STATE"

cat <<EOF

[✓] 一次性 ECS 就绪
    InstanceId : $IID
    PublicIP   : $IP
    自动释放   : $RELEASE(预算护栏：到点自毁)
    SSH        : ssh -i $KEY_FILE root@$IP
    同步代码   : rsync -az -e "ssh -i $KEY_FILE" --exclude .git --exclude __pycache__ \\
                   "$ROOT/" root@$IP:~/AgentSkillsHack/
    跑隔离实验 : ssh -i $KEY_FILE root@$IP 'cd AgentSkillsHack && ./sandbox/run_sandbox.sh'

[!] 用完即焚： ./deploy/aliyun/teardown.sh
EOF
