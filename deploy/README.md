# Deploy — 把整套实验放到一次性云 VM,主机彻底不进循环

为什么用云 VM:你担心"电脑被纳入这个循环"。最干净的边界不是容器,而是**一台用完即焚的云虚拟机**——
你的笔记本只负责 SSH;agent 自创技能、跑脚本、试图外泄,统统发生在那台一次性 VM 的容器里。

## 推荐姿势(双重隔离 = T3)

```
你的笔记本 ──SSH──▶ 一次性云 VM(AWS/Aliyun) ──▶ Docker 隔离容器(本仓库 sandbox/)
   只发指令              host 是它,不是你           non-root/只读/出网允许列表
```

## 三步走

1. **起一台一次性 VM**,用 `cloud-init.yaml` 作 user-data 自动装好 Docker:
   - AWS: 见 [`aws/README.md`](aws/README.md)(含 `launch.sh`)
   - Aliyun: 见 [`aliyun/README.md`](aliyun/README.md)
2. **把代码同步上去**(代码不在公共远端,故用 rsync):
   ```bash
   rsync -az --exclude .git --exclude '__pycache__' ./ lab@<VM_IP>:~/AgentSkillsHack/
   ```
3. **在 VM 上、容器内运行**:
   ```bash
   ssh lab@<VM_IP>           # Aliyun 默认 root@<IP>
   cd ~/AgentSkillsHack
   ./sandbox/run_sandbox.sh                       # 离线攻防 demo,零出网
   # ---- 真实 OpenClaw + 真实 LLM(出网锁定,只放行 LLM 域名) ----
   cp sandbox/.env.example sandbox/.env           # 填 LLM_API_KEY / 模型 / EGRESS_ALLOW
   make oc-build && make oc-up                     # 在 ECS 上构建并启动锁定沙箱
   make oc-ask MSG="你好"                           # OpenClaw 用真实模型回答
   ./sandbox/skillctl.sh add sandbox/skills/weather  # Cisco 扫描门 + 你批准
   ```
   > OpenClaw 在 ECS 上的运行与本机完全一致(同一套容器)——ECS 只是把"宿主"从你的笔记本换成一次性云 VM。
   > 出网锁定(egress_proxy)确保 OpenClaw 即便加载恶意技能也偷不到云元数据/凭据、传不出去。
4. **用完即焚**(见各 runbook 的 teardown):销毁实例 + 安全组 + 密钥,避免遗留与计费。

## 隔离责任分层

| 控制点 | 由谁强制 | 作用 |
|---|---|---|
| 入站 | 云安全组 | 只允许你的 IP SSH(22),其余全拒 |
| 出站(粗) | 云安全组 / VPC | 默认可全开;高安全场景收窄到 LLM 端点 IP 段 |
| 出站(细) | 容器内 squid 允许列表 | agent 只能访问你配置的那一个 LLM 域名 |
| 进程 | 容器 hardening | 非 root/只读根/丢能力/no-new-privileges/资源限额 |
| 数据 | canary-only + 内网 collector | 任何"外泄"只打到内网蜜罐,无真实数据离开 |

## 成本与安全提醒

- 选最小够用的机型(2 vCPU/4–8GB 足够跑框架;真实 agent 若要本地模型另算 GPU)。
- **API key 只在运行时经 env 注入**,绝不写进 user-data / 镜像 / git。
- 实例打上 `auto-terminate` 思路:实验完立即销毁;可设预算告警。
- 一律 canary-only,遵守 [ETHICS.md](../ETHICS.md);不要对真实注册表/真实凭据动手。
