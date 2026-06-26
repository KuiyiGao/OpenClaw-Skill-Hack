# SkillSpector vs `agent-skill-firewall` — A Grounded Comparison

> Companion to the [README](../README.md). README has the pitch; this
> document has the bench data, the architecture diff, and the caveats.
> Bilingual (EN / 中文); the two halves cover the same ground at
> different lengths.

---

## 1. Local benchmark

Five testcases (1 benign + 4 malicious). SkillSpector run in
`--no-llm` mode (its deterministic static path); our L0 = `firewall scan`;
our IAR = `firewall watch` against a synthetic captured-egress log
(`EGRESS capture POST attacker-canary.evil /exfil`).

| # | Case | Truth | SkillSpector v2.3.7 (`--no-llm`) | Our L0 | Our IAR |
|---|---|---|---|---|---|
| 1 | `weather-safe` | benign | SAFE  (score 0,  0 findings) | NONE | BENIGN (score 5) |
| 2 | `weather-malicious-canary` | malicious | SAFE  (score 7,  0 findings) | **CRITICAL** (`hostile_host_literal`) | **MALICIOUS** (score 90) |
| 3 | `config-redirect-malicious` | malicious | SAFE  (score 7,  0 findings) | NONE | **MALICIOUS** (score 90) |
| 4 | `hex-encode-malicious` | malicious | SAFE  (score 7,  0 findings) | NONE | **MALICIOUS** (score 90) |
| 5 | `dyn-url-malicious` | malicious | SAFE  (score 10, 0 findings) | NONE | **MALICIOUS** (score 90) |

Confusion matrix (block defined as: SkillSpector `recommendation ≠ SAFE`;
ours `L0 == CRITICAL` or `IAR == MALICIOUS`):

| Detector | TP | FP | TN | FN |
|---|---:|---:|---:|---:|
| SkillSpector (`--no-llm`) | 0 | 0 | 1 | 4 |
| Our L0 alone | 1 | 0 | 1 | 3 |
| Our IAR alone | 4 | 0 | 1 | 0 |
| **Our L0 ∪ IAR** | **4** | **0** | **1** | **0** |

SkillSpector returned `SAFE` on all four malicious cases at this floor.
Its LLM analyzer path was not exercised (no API key configured); a
head-to-head against the full pipeline would be a different number and
we don't claim it here.

The four malicious cases use the same evasion family `attacker-canary.evil`
but reach it differently: a literal in code (#2), via a JSON manifest (#3),
via `bytes.fromhex` (#4), or via `chr()` arithmetic (#5). Cases #3–#5
are static-evasive **by construction** — there is no host string for any
pattern matcher to grep — so we expect SkillSpector to miss them. The
informative result is **case #2**: the host is plain ASCII inside
`scripts/collect.py`. Our L0 catches it (`hostile_host_literal`);
SkillSpector's only finding on that file is `LP3` ("declare permissions in
SKILL.md"), unrelated to the malicious indicator.

### 1. 本地基准（中文）

四个恶意 + 一个良性,共 5 个用例。SkillSpector 在 `--no-llm` 静态档全部
返回 SAFE 放行；我们 L0 抓住 case 2(`attacker-canary` 字面量),运行时层
抓住 case 3-5(主机分别来自 JSON 配置 / 十六进制解码 / `chr()` 拼接,
静态层结构上看不见)。良性 case 1 双方都正确放行。结论:**SkillSpector
在这组用例上抓 0/4,我们 L0 ∪ IAR 抓 4/4,零误杀。**

---

## 2. Why this gap exists — NVIDIA's own scope language

SkillSpector's purpose is **publish-time gating**, not runtime
enforcement. The primary sources state this explicitly:

* The [GitHub README](https://github.com/NVIDIA/skillspector) frames the
  tool around one question — *"Is this skill safe to install?"* — with
  exit codes `0 / 1 / 2` designed as an install gate.
* The [docs page](https://docs.nvidia.com/skills/scanning-agent-skills)
  is titled *"Scan Agent Skills Before Installation"*.
* The same README adds, verbatim: *"It does not sandbox the host."*

Four architectural blockers a scanner cannot get around without becoming
a different product:

1. **No HTTP/network proxy.** SkillSpector is a file scanner
   (regex / AST / YARA / taint / OSV lookup). Nothing in the pipeline
   listens on a socket.
2. **Taint is static-only.** Source→sink edges live in the AST; they
   never propagate across a running tool call.
3. **No sandbox boundary owned by SkillSpector.** The README is explicit
   about this — runtime isolation is OpenShell's job.
4. **One-shot scan, no per-skill workspace.** The tool scans a target
   (directory / git URL / zip) once and exits. There is no long-lived
   process model to attach a verdict ladder to.

### 2. 这个空白怎么来的（中文）

SkillSpector 自己定位是**发布前 gate**:回答"这个技能能不能装",
不是"这次调用能不能放"。NVIDIA 把运行时隔离放到了**另一个产品** OpenShell
里(seccomp / Landlock / eBPF / cgroups 的内核级沙盒),把 LLM 调用内的
内容护栏放到了 NeMo Guardrails 里。SkillSpector README 自己写得很清楚:
*"It does not sandbox the host."*

---

## 3. Architectural comparison

| Dimension | SkillSpector | `agent-skill-firewall` |
|---|---|---|
| Install layer | Pre-install scanner | Runtime behavioural firewall (L0 static + L1 proxy + L2 IAR) |
| Sandbox boundary | None (deferred to OpenShell) | Egress proxy + canary; deny-by-default |
| Taint model | Static AST source→sink | Cross-plane: file-plane read × network-plane send, observed in one run |
| Output format | Terminal / JSON / Markdown / SARIF 2.1.0 | JSONL events + live Textual TUI |
| Policy authoring | 68 built-in patterns across 17 categories; baseline-suppression file | Declarative TOML at `~/.config/firewall/config.toml`; every regex, host list, secret path is user-editable |
| Provenance | NVIDIA-Verified catalog + signed Skill Cards | — |
| License | Apache-2.0 | MIT |

### 3. 架构对比（中文）

两行最该看:**沙盒**和**策略**。SkillSpector 自己不带沙盒,所有边界
控制都靠 OpenShell;我们的 proxy 是沙盒的一部分(网络层),deny-by-default
是设计中心。**策略**:SkillSpector 的 68 条规则你只能"建议",我们的所有
正则 / 主机列表 / 秘密路径**都在你自己 commit 的 TOML 里**,可以 diff,
可以 review。

---

## 4. NVIDIA's actual runtime story

The runtime story is split across two other NVIDIA products:

* **OpenShell** — kernel-level sandbox using seccomp, Landlock, eBPF,
  cgroups. Enforces YAML policies on syscalls (filesystem, network,
  inference). This decides *can this process call `network()`*.
* **NeMo Guardrails** — content guardrails inside the LLM call itself
  (prompt-injection filters, PII, topic boundaries).

What **neither** does: a **per-action intent-vs-action divergence
verdict**. OpenShell can let a `network()` call through; it does not
know whether *that particular* call was inside the skill's declared
purpose. The runtime IAR layer in this package fills that gap.

### 4. NVIDIA 的运行时层在哪（中文）

OpenShell 管 syscall 边界(能不能上网),NeMo Guardrails 管 LLM 调用内
的内容控制。两者**都不**做"per-action intent-vs-action"层级的判决——
那正是我们 IAR 的位置。

---

## 5. When to use which tool

* **SkillSpector** — at publish-time / CI / catalog gating. SARIF output
  drops into GitHub code-scanning, GitLab, IDE security panels. Use it
  if you maintain a skill marketplace or need a CI gate.
* **`agent-skill-firewall`** — at run-time, on the operator's machine.
  Catches what the skill actually does over the network, with a TUI
  that shows verdicts as they happen. Use it if you run agents (your
  own or your team's) and want a fail-closed default.
* **Use both.** SkillSpector at publish time → `agent-skill-firewall`
  at run time. They have orthogonal failure modes; the §1 numbers make
  that concrete.

### 5. 用哪个（中文）

发布前过审用 SkillSpector(SARIF 进 GitHub code-scanning),日常跑 agent
时让本机的 `agent-skill-firewall` 兜底。两者互补,不是替代。

---

## 6. UX impact of running the firewall

From `pip install` to first verdict — 7 steps:

```bash
pip install agent-skill-firewall                 # 1) install
firewall config init                             # 2) write ~/.config/firewall/config.toml
$EDITOR "$(firewall config path)"                # 3) review the TOML
export DEEPSEEK_API_KEY=sk-...                   # 4) set the driver key env var
firewall start                                   # 5) terminal A — proxy + canary live
firewall panel                                   # 6) terminal B — live TUI
eval "$(firewall hook generic)"; openclaw ...    # 7) terminal C — run your agent
```

Latency: proxy adds ~2-10 ms per request on localhost
(`http.server` + ThreadingMixIn, no connection pooling). A verdict
written by L2 is visible in the panel within 250-600 ms (the panel
polls `events.jsonl` every 500 ms).

Three failure modes worth knowing in advance:

| Failure | Blast | Mitigation |
|---|---|---|
| Proxy process crashes | All agents using `HTTP_PROXY` see no egress | `firewall doctor` flags the port; `firewall start` to restart (wrap in a systemd/launchd unit for hard production use) |
| `api_key_env` unset | `firewall start` exits 2 with the env-var name | `firewall doctor` is the first check |
| Agent hits a legitimate host not in `allow_hosts` | HTTPS request fails silently with 403 | Run `firewall config mode observe` for a day; collect host names from `egress.capture` events; add to `allow_hosts`; switch back to `balanced` |

### 6. UX 影响（中文）

从 `pip install` 到看到第一条 verdict 是 7 步、3 个 terminal。延迟人感
不出(本地代理 2-10ms,面板 250-600ms 显示)。真正会咬人的是
`allow_hosts` 配错——HTTPS 调用会被静默 403。**先用 observe 模式跑一天**,
把所有 capture 事件里的主机加白,再切回 `balanced`,这是最稳的 onboarding。

---

## 7. Reproducing this benchmark

The two shipped example skills are enough to reproduce the
SkillSpector-misses-on-the-canary-literal finding (case 2 above):

```bash
# install both
pip install agent-skill-firewall
uv tool install git+https://github.com/NVIDIA/skillspector.git

# bench case 2: the canary host is a plain ASCII literal in collect.py
skillspector scan firewall/examples/skills/weather-malicious-canary --no-llm
firewall scan firewall/examples/skills/weather-malicious-canary

# bench case 1 (benign baseline)
skillspector scan firewall/examples/skills/weather-safe --no-llm
firewall scan firewall/examples/skills/weather-safe
```

Cases 3-5 use research skills that are intentionally not in the public
repo (the `--static-evasive` markers in the original lab would let them
be re-used as attack templates). To reproduce them, author your own
skill where the destination host is sourced from anywhere but a string
literal in code (a JSON config, a hex blob, `chr()` arithmetic), feed
the synthetic egress log to `firewall watch`, and observe `MALICIOUS
score=90` on the IAR plane.

### 7. 复现（中文）

包里随发的 `weather-safe` 和 `weather-malicious-canary` 足以复现 case 2
的核心结论(明文 canary 字面量,SkillSpector 漏)。其余三个 evasive 用例
不放到公开仓库(避免被武器化);自己照葫芦画瓢就能复现——目标主机不
要写成字符串字面量,从 JSON / 十六进制 / `chr()` 任选一种取出即可。

---

## Primary sources

* [NVIDIA SkillSpector — GitHub](https://github.com/NVIDIA/skillspector)
* [NVIDIA developer blog: NVIDIA-Verified Agent Skills Provide Capability Governance for AI Agents](https://developer.nvidia.com/blog/nvidia-verified-agent-skills-provide-capability-governance-for-ai-agents/)
* [docs.nvidia.com — Scan Agent Skills Before Installation](https://docs.nvidia.com/skills/scanning-agent-skills)
* This repo: [`firewall/runtime/firewall.py`](../firewall/runtime/firewall.py) (IAR verifier) and [`tests/unit/test_firewall_invariants.py`](../tests/unit/test_firewall_invariants.py) (5 invariants pinned)
