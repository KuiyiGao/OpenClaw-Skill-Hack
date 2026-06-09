# AWS EC2 —— 一次性隔离实验 VM

目标：起一台**用完即焚**的 EC2,只允许你的 IP SSH,在其中用容器隔离跑实验。你的电脑只 SSH。

## 前置
- 装好并配置 `aws` CLI(`aws configure`)。
- 选好区域,例如 `export AWS_REGION=us-west-2`。

## 一键脚本(推荐)
`launch.sh` 封装全流程(密钥→安全组→起实例→输出 IP),`teardown.sh` 用完即焚:
```bash
export AWS_REGION=us-west-2
./deploy/aws/launch.sh                 # 起一次性 VM
# ...实验...
./deploy/aws/teardown.sh               # 销毁实例/安全组/密钥
```
**预算护栏:** `instance-initiated-shutdown-behavior=terminate` + cloud-init `power_state`
定时关机 → 实例在 `AWS_TTL_HOURS`(默认 8h)后**自动终止**,忘了销毁也不会一直计费。
资源 ID 落盘 `.lab-state.env` 供 teardown 精确清理。可调 `AWS_TTL_HOURS` / `AWS_INSTANCE_TYPE`。

## 手动 runbook(理解每一步)

```bash
# 0) 变量
export AWS_REGION=us-west-2
MYIP=$(curl -s https://checkip.amazonaws.com)        # 你的公网 IP
NAME=asshack-lab

# 1) 最新 Amazon Linux 2023 AMI
AMI=$(aws ssm get-parameters --region $AWS_REGION \
  --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameters[0].Value' --output text)

# 2) 临时密钥对
aws ec2 create-key-pair --region $AWS_REGION --key-name $NAME-key \
  --query KeyMaterial --output text > $NAME-key.pem && chmod 600 $NAME-key.pem

# 3) 安全组：仅允许你的 IP SSH(22),出站默认全开(细粒度出网交给容器内 squid)
SG=$(aws ec2 create-security-group --region $AWS_REGION \
  --group-name $NAME-sg --description "asshack lab" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --region $AWS_REGION \
  --group-id $SG --protocol tcp --port 22 --cidr ${MYIP}/32

# 4) 启动实例(user-data = cloud-init,自动装 Docker)；用完即焚故无需 EBS 持久化
IID=$(aws ec2 run-instances --region $AWS_REGION \
  --image-id $AMI --instance-type t3.small \
  --key-name $NAME-key --security-group-ids $SG \
  --user-data file://deploy/cloud-init.yaml \
  --instance-initiated-shutdown-behavior terminate \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME},{Key=purpose,Value=disposable-security-research}]" \
  --query 'Instances[0].InstanceId' --output text)

# 5) 取公网 IP
aws ec2 wait instance-running --region $AWS_REGION --instance-ids $IID
IP=$(aws ec2 describe-instances --region $AWS_REGION --instance-ids $IID \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "VM ready: lab@$IP"

# 6) 同步代码并运行(在 VM 的容器内)
rsync -az -e "ssh -i $NAME-key.pem" --exclude .git --exclude __pycache__ \
  ./ ec2-user@$IP:~/AgentSkillsHack/
ssh -i $NAME-key.pem ec2-user@$IP 'cd AgentSkillsHack && ./sandbox/run_sandbox.sh'
```

## Teardown(务必执行,用完即焚)
```bash
aws ec2 terminate-instances --region $AWS_REGION --instance-ids $IID
aws ec2 wait instance-terminated --region $AWS_REGION --instance-ids $IID
aws ec2 delete-security-group --region $AWS_REGION --group-id $SG
aws ec2 delete-key-pair --region $AWS_REGION --key-name $NAME-key
rm -f $NAME-key.pem
```

## 加固选项
- 收窄出站:把安全组 egress 改为只允许你的 LLM 端点 IP 段(或全交给容器内 squid 允许列表)。
- 用 SSM Session Manager 替代开放 22 端口(连 SSH 入站都不开)。
- 设 AWS Budgets 预算告警,防遗忘计费。
