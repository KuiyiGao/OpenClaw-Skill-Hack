# 阿里云 ECS 上运行 OpenClaw 隔离实验室 —— 完整使用清单（网页 + 命令）

本清单把"在阿里云一台 VM 上，让真实 OpenClaw 接真实模型、在出网锁定的沙箱里自行运行"的全过程
拆成可照做的步骤。标注 **【网页】**（控制台操作）/ **【命令】**（VM 内执行）。

> 隔离模型：你的电脑只负责 SSH；OpenClaw 跑在 ECS 上的容器里，出网被锁死到只剩 LLM 域名。
> 配一次、装一堆技能、反复重启都行（状态在持久卷里）；做完再释放实例。

---

## 0. 你需要什么
- 一个已实名认证、可计费的阿里云账号。
- 一个真实 LLM 的 API key（OpenAI / 兼容 OpenAI 的端点 / 阿里云百炼 DashScope 等）。
- 本机一个浏览器；可选：SSH 客户端（macOS/Linux 自带 `ssh`，Windows 用 PowerShell/MobaXterm）。

---

## 1. 设预算护栏（避免忘记关机烧钱）
- **【网页】** 控制台右上角头像 → **费用与成本 → 预算管理 → 新建预算**：设月度预算 + 邮件/短信告警阈值。
- **【网页】** 充值少量余额（按量付费，2 vCPU/4G + 5Mbps 带宽，一天通常几元）。

---

## 2. 创建一台一次性 ECS（网页）
- **【网页】** 控制台 → **云服务器 ECS → 实例 → 创建实例**（选"自定义购买"）。按下表选：

| 项 | 选择 |
|---|---|
| 付费模式 | **按量付费**（用完即释放） |
| 地域/可用区 | 选离你近的（如 华东1·杭州）；记住地域 |
| 实例规格 | **2 vCPU / 4 GiB**（如 `ecs.e-c1m2.large` 或经济型 `ecs.e`）|
| 镜像 | 公共镜像 → **Ubuntu 22.04 64 位** |
| 系统盘 | 40 GiB ESSD Entry/云盘（够用） |
| 公网 IP | **勾选"分配公网 IPv4 地址"**；带宽计费选"按使用流量"，峰值 5 Mbps |
| 安全组 | 新建或选默认（下一步收紧入方向） |
| 登录凭证 | **密钥对**（推荐，新建并下载 `.pem`）或自定义密码 |
| 实例名称 | 如 `openclaw-lab` |

- **【网页】** 展开"高级选项"→ 可设 **释放保护关闭** + **定时释放时间**（如 +8 小时自动释放，双保险）。
- **【网页】** 确认订单 → **创建实例**。回到实例列表，记下该实例的 **公网 IP**。

---

## 3. 收紧安全组：只放行你的 IP 的 SSH（网页）
默认安全组常对 `0.0.0.0/0` 放行 22 端口，**必须收紧**：
- **【网页】** 实例详情 → **安全组 → 配置规则 → 入方向 → 手动添加**：
  - 协议类型 **SSH(22)**；授权对象填 **你的公网 IP/32**（浏览器搜"我的 IP"获取）。
  - 删除/收紧任何 `0.0.0.0/0` 的 22 放行规则。
- 出方向：保持默认全放行即可——**细粒度出网由 VM 内的容器代理（egress_proxy）控制**，比安全组更精准。

---

## 4. 连接实例（二选一）
- **【网页】**（最简单，无需本地 SSH）：实例 → **远程连接 → Workbench**（一键登录）→ 浏览器内终端，用户名 `root`。
- **【命令】**（本地 SSH，密钥方式）：
  ```bash
  chmod 600 ~/Downloads/openclaw-lab.pem
  ssh -i ~/Downloads/openclaw-lab.pem root@<你的公网IP>
  ```

---

## 5. 在 VM 上装好 Docker（命令）
```bash
curl -fsSL https://get.docker.com | sh      # 安装 Docker
systemctl enable --now docker               # 开机自启 + 启动
docker version                              # 验证
apt-get update && apt-get install -y git rsync   # 取代码用
```

---

## 6. 把代码放到 VM（三选一）
- **【命令·git】** 若代码在你的 Git 仓库：
  ```bash
  git clone <你的仓库地址> AgentSkillsHack && cd AgentSkillsHack
  ```
- **【命令·本地 rsync】** 在**你本机**执行，把本地目录同步上去：
  ```bash
  rsync -az -e "ssh -i ~/Downloads/openclaw-lab.pem" \
    --exclude .git --exclude __pycache__ --exclude 'sandbox/.env' \
    ./AgentSkillsHack/ root@<你的公网IP>:~/AgentSkillsHack/
  ```
- **【网页】** Workbench 终端右上角有"上传文件"，可直接把打包好的 zip 传上去再解压。

---

## 7. 配置真实 LLM（命令）
```bash
cd ~/AgentSkillsHack
cp sandbox/.env.example sandbox/.env
nano sandbox/.env          # 填写下面四项 + 出网白名单
```
`sandbox/.env` 要点：
```
LLM_API_KEY=sk-你的真实key          # 唯一进入容器的凭据
LLM_MODEL=gpt-4o-mini               # 模型 id
LLM_BASE_URL=https://api.openai.com/v1   # 你的 LLM 端点（兼容 OpenAI）
LLM_API=openai-responses
EGRESS_ALLOW=api.openai.com         # 只放行这个域名出网；换 provider 要同步改
```
> 用阿里云百炼/DashScope 等兼容端点：把 `LLM_BASE_URL` 改成其兼容地址，`EGRESS_ALLOW` 改成其域名即可。

---

## 8. 构建并启动 OpenClaw 锁定沙箱（命令）
```bash
make oc-build      # 构建 OpenClaw 镜像（容器内 Node24 + npm i -g openclaw，约几分钟）
make oc-up         # 启动：egress-proxy + canary + openclaw（常驻）
make oc-ask MSG="用一句话介绍你自己"   # OpenClaw 用真实模型回答 → 看它的反应
```

---

## 9. 监控 + 你决定放哪些技能（命令）
```bash
# 监控入口：实时看 OpenClaw 反应 / canary 命中 / 被拦截的外泄尝试
make oc-monitor

# 技能门控（Cisco 扫描门 + 你批准）：
./sandbox/skillctl.sh list                          # 已装技能
./sandbox/skillctl.sh scan sandbox/skills/meeting-notes   # 只扫描，给严重度
./sandbox/skillctl.sh add  sandbox/skills/weather   # 干净 → 装入；HIGH/CRITICAL → 拒绝
./sandbox/skillctl.sh add  <你的技能目录> --force    # 你明确批准时强制装入（科研用）
```

---

## 10. 验证"代码保险"：OpenClaw 接触不到外部凭据（命令）
```bash
ex(){ docker compose -f sandbox/docker-compose.yml --env-file sandbox/.env exec -T openclaw bash -lc "$1"; }
ex 'curl -s -o /dev/null -w "LLM(应放行): %{http_code}\n" --max-time 10 https://api.openai.com/v1/models'
ex 'curl -s -o /dev/null -w "外泄(应拒绝): %{http_code}\n" --max-time 8 https://example.com'
ex 'curl -s -o /dev/null -w "阿里云元数据(应拒绝): %{http_code}\n" --max-time 6 http://100.100.100.200/latest/meta-data/'
```
预期：LLM 域名连通（真实 key 时返回 200/正常）；其它一律 `000`（被代理拒绝），
即便恶意技能读到 `LLM_API_KEY` 也传不出去、也偷不到阿里云实例 RAM 角色临时凭据。

---

## 11. 反复使用 / 重启（不必重建 VM）
- 技能与配置存在持久卷 `openclaw-state`，`make oc-down` 后 `make oc-up` 不丢。
- **测一批技能 → `make oc-down` → 改 `.env`/换技能 → `make oc-up`** 即可，无需重开实例。
- 只有彻底做完，才进入第 12 步释放实例。

---

## 12. 用完即焚：释放实例（网页 + 命令）
- **【命令】** 先停容器：`make oc-down`
- **【网页】** ECS 实例列表 → 勾选实例 → **释放设置 / 立即释放**（按量付费实例释放即停止计费）。
- **【网页】** 顺手清理：**弹性公网 IP / 安全组 / 密钥对**（如为本次新建）。
- 若用了 CLI 一键脚本，可直接 `./deploy/aliyun/teardown.sh` 精确清理本次新建的资源。

---

## 安全须知
- `LLM_API_KEY` 只放在 VM 的 `sandbox/.env`（已 gitignore），**不要提交到仓库**。
- 出网锁定 + 非 root + 只读根 + 不挂主机密钥：即使加载恶意/未知技能，也限制其外泄与提权。
- 一律 canary-only（内置 mock 技能的"攻击"端点不可达且被锁），见仓库根 `ETHICS.md`。
- 一键 CLI 路径见 [`README.md`](README.md)（`launch.sh` / `teardown.sh`，含自动释放预算护栏）。
