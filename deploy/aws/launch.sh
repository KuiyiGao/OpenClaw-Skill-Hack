#!/usr/bin/env bash
# 一键起一台【一次性】AWS EC2 隔离实验 VM。读完 deploy/aws/README.md 再运行。
#
# 预算护栏：
#   - instance-initiated-shutdown-behavior=terminate + cloud-init power_state 定时关机
#     → 实例在 AWS_TTL_HOURS 小时后【自动终止】(默认 8h)，忘了销毁也不会一直计费。
#   - 最小机型 t3.small；新建资源 ID 落盘 .lab-state.env 供 teardown.sh 精确清理。
#
# 用法：  export AWS_REGION=us-west-2 ; ./deploy/aws/launch.sh   ; ...  ; ./deploy/aws/teardown.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
STATE="$HERE/.lab-state.env"

: "${AWS_REGION:?请先 export AWS_REGION，例如 us-west-2}"
NAME="${AWS_NAME:-asshack-lab}"
TYPE="${AWS_INSTANCE_TYPE:-t3.small}"
TTL_HOURS="${AWS_TTL_HOURS:-8}"

command -v aws  >/dev/null || { echo "需要 aws CLI"; exit 1; }
command -v curl >/dev/null || { echo "需要 curl"; exit 1; }
[ -f "$STATE" ] && { echo "已存在 $STATE，疑似未清理。请先 ./deploy/aws/teardown.sh"; exit 1; }

MYIP="$(curl -s https://checkip.amazonaws.com)"
echo "==> region=$AWS_REGION  type=$TYPE  your-ip=$MYIP  auto-terminate=+${TTL_HOURS}h"

AMI="$(aws ec2 describe-images --region "$AWS_REGION" --owners amazon \
  --filters 'Name=name,Values=al2023-ami-*-x86_64' 'Name=state,Values=available' \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)"
echo "==> AMI=$AMI"

# 预算护栏：在共享 cloud-init 末尾追加 power_state 定时关机(top-level key，安全可追加)
UD="$(mktemp)"; trap 'rm -f "$UD"' EXIT
cat "$ROOT/deploy/cloud-init.yaml" > "$UD"
cat >> "$UD" <<EOF

power_state:
  mode: poweroff
  delay: '+$((TTL_HOURS*60))'
  condition: true
EOF

aws ec2 create-key-pair --region "$AWS_REGION" --key-name "$NAME-key" \
  --query KeyMaterial --output text > "$HERE/$NAME-key.pem"
chmod 600 "$HERE/$NAME-key.pem"

SG="$(aws ec2 create-security-group --region "$AWS_REGION" \
  --group-name "$NAME-sg" --description 'asshack disposable lab' \
  --query GroupId --output text)"
aws ec2 authorize-security-group-ingress --region "$AWS_REGION" \
  --group-id "$SG" --protocol tcp --port 22 --cidr "${MYIP}/32" >/dev/null

IID="$(aws ec2 run-instances --region "$AWS_REGION" \
  --image-id "$AMI" --instance-type "$TYPE" \
  --key-name "$NAME-key" --security-group-ids "$SG" \
  --user-data "file://$UD" \
  --instance-initiated-shutdown-behavior terminate \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME},{Key=purpose,Value=disposable-security-research}]" \
  --query 'Instances[0].InstanceId' --output text)"

cat > "$STATE" <<EOF
AWS_REGION=$AWS_REGION
INSTANCE_ID=$IID
SECURITY_GROUP_ID=$SG
KEY_PAIR_NAME=$NAME-key
KEY_FILE=$HERE/$NAME-key.pem
EOF

aws ec2 wait instance-running --region "$AWS_REGION" --instance-ids "$IID"
IP="$(aws ec2 describe-instances --region "$AWS_REGION" --instance-ids "$IID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
echo "PUBLIC_IP=$IP" >> "$STATE"

cat <<EOF

[✓] 一次性 EC2 就绪
    InstanceId : $IID
    PublicIP   : $IP
    自动终止   : +${TTL_HOURS}h(预算护栏)
    SSH        : ssh -i $HERE/$NAME-key.pem ec2-user@$IP
    同步代码   : rsync -az -e "ssh -i $HERE/$NAME-key.pem" --exclude .git --exclude __pycache__ \\
                   "$ROOT/" ec2-user@$IP:~/AgentSkillsHack/
    跑隔离实验 : ssh -i $HERE/$NAME-key.pem ec2-user@$IP 'cd AgentSkillsHack && ./sandbox/run_sandbox.sh'

[!] 用完即焚： ./deploy/aws/teardown.sh
EOF
