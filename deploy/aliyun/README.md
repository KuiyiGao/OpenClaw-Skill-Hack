# 阿里云 ECS —— 一次性隔离实验 VM

与 AWS 同构：起一台**用完即焚**的 ECS,安全组只放行你的 IP SSH,内部用容器隔离跑实验。

> 📋 **完整使用清单（网页控制台操作 + 命令，含在 ECS 上跑真实 OpenClaw + 真实模型）：见 [USAGE.md](USAGE.md)。**
> 本文件是 CLI 一键脚本路径，适合已装 `aliyun` CLI 的用户。

## 一键脚本(推荐)

```bash
aliyun configure                      # 配置 AccessKey/Secret
export ALI_REGION=cn-hangzhou
./deploy/aliyun/launch.sh             # 自动:网络→安全组→密钥→镜像→起实例→输出 IP
# ...实验(SSH 上去,容器内跑 ./sandbox/run_sandbox.sh)...
./deploy/aliyun/teardown.sh           # 用完即焚:实例/安全组/密钥/临时网络 全清
```

**预算护栏(防忘记销毁烧钱):**
- `AutoReleaseTime`:实例在 `ALI_TTL_HOURS`(默认 8h)后**自动释放**——双保险,即使不跑 teardown 也不会一直计费。
- 按量付费 + 按流量带宽 + 最小机型;所有新建资源 ID 落盘 `.lab-state.env`,teardown 据此精确清理(只删自建网络,复用的默认 VPC 不动)。
- 可调:`ALI_TTL_HOURS` / `ALI_INSTANCE_TYPE` / `ALI_IMAGE_ID` / `ALI_VSWITCH_ID`(指定则复用,不自建网络)。

> 依赖:本机需 `aliyun`、`jq`、`curl`。下面是手动 runbook,用于理解每一步。

## 前置(手动 runbook)
- 装好并配置阿里云 CLI:`aliyun configure`(AccessKey/Secret/Region)。
- 选 region,例如 `export ALI_REGION=cn-hangzhou`。

## Runbook(aliyun CLI)

```bash
# 0) 变量
export ALI_REGION=cn-hangzhou
NAME=asshack-lab
MYIP=$(curl -s https://checkip.amazonaws.com)

# 1) 找一个 Ubuntu/Alinux 镜像 ID(示例查 Ubuntu 22.04)
IMAGE=$(aliyun ecs DescribeImages --RegionId $ALI_REGION \
  --OSType linux --ImageOwnerAlias system \
  --query 'Images.Image[?contains(OSName,`Ubuntu  22.04`)].ImageId | [0]' --output text)

# 2) 安全组 + 只放行你的 IP 的 22 端口
SG=$(aliyun ecs CreateSecurityGroup --RegionId $ALI_REGION \
  --SecurityGroupName $NAME-sg --query SecurityGroupId --output text)
aliyun ecs AuthorizeSecurityGroup --RegionId $ALI_REGION --SecurityGroupId $SG \
  --IpProtocol tcp --PortRange 22/22 --SourceCidrIp ${MYIP}/32 --Policy accept
# 出站默认放行;高安全可改 AuthorizeSecurityGroupEgress 收窄到 LLM 端点

# 3) 需要一个 vSwitch(VPC 子网)ID。若无,先建 VPC/vSwitch,或用控制台默认网络的 vSwitchId
VSW=<your-vswitch-id>

# 4) base64 编码 cloud-init 作为 UserData
UD=$(base64 -i deploy/cloud-init.yaml | tr -d '\n')

# 5) 创建实例(按量付费,用完即焚;公网带宽 5Mbps 足够)
IID=$(aliyun ecs RunInstances --RegionId $ALI_REGION \
  --ImageId $IMAGE --InstanceType ecs.e-c1m2.large \
  --SecurityGroupId $SG --VSwitchId $VSW \
  --InternetMaxBandwidthOut 5 --InstanceChargeType PostPaid \
  --Amount 1 --UserData "$UD" \
  --InstanceName $NAME --query 'InstanceIdSets.InstanceIdSet[0]' --output text)

# 6) 取公网 IP(稍等实例 Running)
aliyun ecs DescribeInstances --RegionId $ALI_REGION --InstanceIds "['$IID']" \
  --query 'Instances.Instance[0].PublicIpAddress.IpAddress[0]' --output text
```

> 注:首次需设置实例密码或绑定密钥对(`aliyun ecs CreateKeyPair` + RunInstances 加 `--KeyPairName`)。
> 各账号 VPC/vSwitch/镜像 ID 不同,上面留了占位,按你的环境替换。

## 同步代码并运行(同 AWS)
```bash
rsync -az --exclude .git --exclude __pycache__ ./ root@<IP>:~/AgentSkillsHack/
ssh root@<IP> 'cd AgentSkillsHack && ./sandbox/run_sandbox.sh'
```

## Teardown(用完即焚)
```bash
aliyun ecs DeleteInstance --RegionId $ALI_REGION --InstanceId $IID --Force true
aliyun ecs DeleteSecurityGroup --RegionId $ALI_REGION --SecurityGroupId $SG
# 如建了临时 VPC/vSwitch/KeyPair,一并删除
```

## 加固选项
- 出站收窄:用安全组 Egress 规则只放行 LLM 端点,其余 deny;细粒度仍交给容器内 squid 允许列表。
- 用 ECS"会话管理/云助手"替代开放 22。
- 设费用预算与到期释放,避免遗忘计费。
