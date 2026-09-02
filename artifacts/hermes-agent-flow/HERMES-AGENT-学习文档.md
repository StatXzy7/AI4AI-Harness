# HERMES Agent 学习文档 —— 配合《HERMES Agent 整体流程》图使用

> 生成日期：2026-09-01
> 流程图：[hermes-agent-workflow.html](./hermes-agent-workflow.html)
> 信息来源：Nous Research 官方文档站（hermes-agent.nousresearch.com，Architecture / Memory / Skills 页面）。本文所有组件名、文件名、函数名均来自官方文档原文，未经改写。

---

## 1. HERMES Agent 是什么

HERMES Agent（昵称"爱马仕"）是 Nous Research 于 2026 年 2 月开源的自托管自主 AI 智能体，MIT 协议。官方定位是 **"会自我改进的 AI agent"（the self-improving AI agent）**：它不是一次性聊天机器人，而是一个长期在线、越用越聪明的"数字员工"。

一句话理解它的差异点：**大多数 Agent 框架的卖点是"会用工具"，HERMES 的卖点是"会从经验中学习"**——它有一个内建的学习闭环（learning loop），把每次对话的经验沉淀为持久记忆和可复用技能，供以后所有会话使用。

资源量级（截至本文撰写）：70+ 内置工具 / 28 个工具集、18+ 模型提供商、25+ 消息平台适配器、6-7 种终端执行后端、约 25,000 个测试。

---

## 2. 打开流程图，按主链路走一遍

流程图按"一次消息的生命周期"组织，共四条泳道：**入口 → Agent 核心 → 工具与安全 → 记忆与技能**。主链路（图中加粗强调的路径）是：

```
接入层 Gateway → AIAgent 核心循环 → Prompt Builder → Runtime Provider → 最终回复
```

### 2.1 接入层 Gateway（一切从消息事件开始）

同一个平台无关的核心（`AIAgent.run_conversation()`，位于 `agent/run_agent.py`）服务于四类入口：

| 入口 | 流程 |
|---|---|
| **CLI** | 用户输入 → `HermesCLI.process_input()` → `run_conversation()` → 展示 → 存入 SessionDB |
| **Gateway（25+ 平台）** | 平台事件 → `Adapter.on_message()` → `GatewayRunner._handle_message()` → 鉴权用户 → 解析会话键 → 带会话历史创建 AIAgent → 回复经 Adapter 送回原平台 |
| **ACP 适配器** | VS Code / Zed / JetBrains 等 IDE 通过 stdio/JSON-RPC 接入 |
| **Cron 定时任务** | 调度器 tick → 从 `jobs.json` 载入到期任务 → 创建**无历史**的全新 AIAgent → 挂载技能作为上下文 → 运行 → 送达目标平台 → 更新 `next_run`。注意：Cron 跑的是"一等公民 Agent 任务"而非 shell 任务 |

其他入口还包括 Batch Runner、API Server 和 Python 库调用。

### 2.2 Prompt Builder（为什么你的提示词永远不会"变味"）

`prompt_builder.build_system_prompt()` 按 **稳定 → 上下文 → 易变** 三层组装系统提示，配合 prompt caching。设计约束非常明确：**除 `/model` 切换外，不做任何会打破前缀缓存的变更**。这就是为什么记忆快照在会话中途"冻结"（见 §4）——保证 LLM 的前缀缓存命中，省钱且提速。

### 2.3 Runtime Provider（模型无关层）

`runtime_provider.resolve_runtime_provider()` 解析出实际后端，支持 18+ 提供商（Nous Portal、OpenRouter、OpenAI 或任意 endpoint），兼容 3 种 API 模式：`chat_completions`、`codex_responses`、`anthropic`。

### 2.4 工具循环与审批（图中的安全支路）

当模型返回 `tool_calls`，`model_tools.handle_function_call()` 接管：

- **Tool Registry（`tools/registry.py`）**：所有工具文件在 import 时自注册，零手工清单；70+ 工具 / 28 工具集。
- **工具后端**：终端（local / Docker / SSH / Daytona / Modal / Singularity / Vercel Sandbox）、浏览器（5 后端 10 工具）、Web（4 后端）、MCP（动态）、文件与视觉等。
- **命令审批（`tools/approval.py`）**：危险命令先检测，需要用户批准才执行——即图中"危险命令? → 批准后执行"的安全回边。
- **结果回填**：工具结果返回 Provider 继续推理，循环往复，直到模型不再发起 `tool_calls`，输出最终回复。
- **委托**：`delegate_tool.py` 可派生隔离子 Agent 并行干活；`execute_code` 支持把整条工具管道折叠成一次推理调用（Programmatic Tool Calling）。

---

## 3. 学习闭环（HERMES 的灵魂）

图右下方的"自我改进闭环"是理解 HERMES 的关键。**每一轮对话结束后**，会 fork 一个后台辅助调用（background review），审视刚才这一轮，然后写两样东西：

1. **记忆条目**：通过记忆工具 `add / replace / remove` 写入 `~/.hermes/memories/` 下的两个文件：
   - `MEMORY.md` —— 环境事实、约定、教训（上限 2,200 字符 ≈ 800 tokens）
   - `USER.md` —— 用户偏好、沟通风格（上限 1,375 字符 ≈ 500 tokens）
2. **技能**：通过 `skill_manage` 工具 `create / patch` 技能。系统提示会在三种情况下主动要求它沉淀技能：摸索出值得复用的多步工作流、踩坑后找到正确路径、被用户纠正过做法。

两层防护值得注意：写错不会撑爆——记忆超额时工具直接报错，要求 Agent **在同一轮内先合并/删除再重试**；写错不会立即生效——开启 `write_approval` 后所有写入（包括后台 review 的写入）进入 `~/.hermes/pending/` 等人审批（`/memory pending`、`/skills pending`、`/skills diff`、`/skills approve`）。

---

## 4. 三层记忆体系（对比着记最不容易忘）

| 层 | 载体 | 何时进上下文 | 适合存什么 |
|---|---|---|---|
| **声明式记忆** | MEMORY.md / USER.md | 会话开始注入，**会话内冻结**（保前缀缓存） | 小而常驻的事实，~1,300 tokens |
| **程序性记忆（技能）** | `~/.hermes/skills/` 的 SKILL.md | **按需 3 级渐进披露**：L0 索引 ~3k tokens 常驻 → L1 整篇 → L2 单个参考文件 | 可复用的多步骤流程 |
| **情景记忆（会话检索）** | SQLite + FTS5（`~/.hermes/state.db`） | 完全不常驻，`session_search` 工具按需查 | "我们上周聊过 X 吗？"，约 20ms、零 LLM 调用、零 token 成本 |

技能系统的其他要点：

- 兼容 agentskills.io 开放标准；每个技能同时是一个斜杠命令（`/gif-search funny cats`），最多 5 个技能命令可叠在一条消息里。
- `/learn` 可把任何可描述的东西（本地 SDK 目录、文档 URL、粘贴的笔记、整本书）变成技能；大源会构建成"知识库技能"——精简 SKILL.md + 每主题一个蒸馏文件，查询成本正比于答案而非源的大小。
- Skills Hub 支持从官方源、skills.sh、GitHub taps 等多渠道安装，全部过安全扫描（防数据外传、提示注入、破坏性命令）；用户改过的技能不被更新覆盖。
- 项目级技能（`<repo>/.hermes/skills/` 或 `.agents/skills/`）优先级最高，但需 `hermes skills trust` 并隔离扫描。

---

## 5. 值得抄的设计原则（做 Agent 研究最有含金量的一节）

官方 Architecture 页明确列出的原则，每一条都值得细品：

1. **平台无关核心**：一个 AIAgent 服务所有入口，接入层只做鉴权和会话解析。
2. **提示稳定性**：系统提示绝不中途变异（除 `/model`），一切动态信息靠"下个会话再生效"换缓存命中。
3. **可观察执行**：过程可追踪，trajectory 以 ShareGPT 格式导出，可直接喂给 Atropos 做 RL 训练。
4. **可中断**：长任务可打断。
5. **松耦合**：注册表模式 + `check_fn` 条件门控，工具自注册。
6. **Profile 隔离**：每个 profile 独立 `HERMES_HOME`；两个 Agent 共用同一 home 会互相写坏记忆条目（要共享记忆请用外部 provider）。
7. **记忆与技能分工**：记忆放"小而常在"的事实，技能放"长而按需"的流程——这是它自我改进闭环不炸上下文的关键。

---

## 6. 上手路径（10 分钟）

```bash
# 1. 安装（官方脚本）后自检
hermes doctor

# 2. 记忆系统可选外接 provider（Honcho 等 8 种）
hermes memory setup

# 3. 技能管理
hermes skills browse / install / audit

# 4. 桌面版（官方原生 app）或直接 CLI / 接入 Telegram、Discord 等
```

延伸阅读（官方文档站）：
- 架构总览：https://hermes-agent.nousresearch.com/docs/developer-guide/architecture
- 记忆系统：https://hermes-agent.nousresearch.com/docs/user-guide/features/memory
- 技能系统：https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
- 全量文档（给 LLM 看的）：https://hermes-agent.nousresearch.com/llms-full.txt

---

## 7. 图的阅读提示

- 图中**实线粗箭头** = 主链路；**虚线** = 记忆/技能/学习支路；**红色** = 安全审批路径。
- 交互版 HTML 支持主题切换（明/暗）、缩放、搜索、关系追踪；右上角"章节"下拉可按四个视角过滤：主链路 / 工具循环与审批 / 自我改进闭环 / 记忆体系。
- 为控制版面，图中将"记忆（MEMORY.md/USER.md）"与"技能（SKILL.md）"合并为一个节点展示，两者的详细分工见本文 §3、§4；SessionDB 的"对话落盘"写入路径未画边（避免跨泳道长边），以卡片和本文 §4 说明。
