# ARIS 学习文档 — 自主科研系统（梦中科研）整体流程导读

> 配套图：[`aris-overview.html`](./aris-overview.html)（用 archify skill 生成的可交互流程图，支持明暗主题、缩放、焦点视图、导出）
> 图规格源：[`aris-workflow.json`](./aris-workflow.json)
> 本文档基于 ARIS 仓库 `docs/ARIS_INTRO.md` 与 `skills/` 目录整理，仓库位于 `Auto-claude-code-research-in-sleep/`。

---

## 1. ARIS 是什么（30 秒版）

**ARIS**（Autonomous Research via Adversarial Multi-Agent Collaboration，中文绰号"梦中科研"）是一组 **82 个可组合的 Claude Code skill**（Markdown 文件），把一次科研投稿的完整生命周期——找 idea → 跑实验 → 审稿改稿 → 写论文 → rebuttal → 换会重投 → 做报告——交给 AI 自动编排。

它最核心的设计只有一句话：

> **执行者和审稿人必须来自不同模型家族，且每轮审稿用全新 thread。**

- **执行者**：Claude Code——读文件、写代码、上 GPU 跑实验、改论文。
- **审稿人**：GPT-5.6-Sol（通过 Codex MCP 接入）——冷读产物、按 1-10 打分、列弱点清单。
- **跨家族不变量**：同一个模型审自己写的东西会陷入局部最优（自己写的 bug 自己看不见），所以执行/评审两条线绝不共享模型血统。没有 OpenAI API 时可以换 DeepSeek / Gemini 做免费审稿人。

为什么叫"梦中科研"？因为最出名的用法是 **Workflow 2**：睡前人工签核一次，系统整夜自主循环"审稿→修复→重跑实验→再审稿"，醒来看到分数从 5/10 涨到 7.5/10。

---

## 2. 整体流程图怎么读

打开 `aris-overview.html`，图分 **4 条泳道**（对应图中的横向分层），**6 列**（对应时间推进）：

| 泳道 | 角色 | 说明 |
|------|------|------|
| 人类研究员 | 决策与签核 | 只做三件事：给方向、睡前签核、验收结果 |
| 执行者 · Claude Code | 干活 | 7 条工作流（W1/W1.5/W2/W3/W4/W5+6）全在这一条泳道上 |
| 跨模型审稿 · Codex MCP | 对抗审查 | GPT-5.6-Sol，每轮 fresh thread |
| 审计 · 记忆 | 完整性门 + 外环记忆 | 三层审计链、research-wiki、meta-optimize |

**主线（粗箭头）**是：研究员 → W1 idea-discovery → W1.5 experiment-bridge → W2 auto-review-loop → W3 paper-writing → 三层审计链 → W4 rebuttal → W5 resubmit / W6 talk。

**支线**：
- 实验桥接和审稿循环都会把工作发给审稿人（安全/虚线边），审稿人把"弱点清单 + 分数"返回；
- W1 的失败 pilot 写入 research-wiki（"失败 ⇄ 反重复记忆"），供下次找 idea 时绕开；
- 各工作流把运行日志写进 `events.jsonl`，meta-optimize 定期读取并（经审稿人把关）改进 SKILL.md 本身。

HTML 里预置了 4 个"章节视图"，可以直接点看：
1. **全生命周期** —— 主线八步；
2. **对抗审稿环** —— Claude 执行 × GPT 审稿的循环细节；
3. **完整性审计门** —— 三层审计 + citation/kill-argument 附加层；
4. **记忆与外环进化** —— wiki 与 meta-optimize 两个"越用越聪明"的机制。

---

## 3. 七条工作流逐个拆解

### W1 · `/idea-discovery`（找 idea）
> 输入：一句模糊的研究方向。输出：排过序、且被 GPU pilot 验证过的提案。

1. **文献调研**：多源检索（Zotero / Obsidian / arXiv / Semantic Scholar / DeepXiv / Exa）建领域地图；
2. **头脑风暴**：GPT 生成 8-12 个锚定在已知 gap 上的具体 idea；
3. **查新**：每个 idea 过 arXiv + DBLP，撞车的当场杀掉；
4. **Pilot**：幸存的 2-3 个 idea 各跑 1-2 小时单卡实验——**用真实信号替代 LLM 的自我感觉**；
5. **精炼**：最好的结果交给 `/research-refine`，产出 `EXPERIMENT_PLAN.md`，直接喂给 W1.5。

失败 pilot 同样入库（research-wiki），变成下次的反重复记忆。

### W1.5 · `/experiment-bridge`（实验桥接）
> 输入：`EXPERIMENT_PLAN.md`。输出：跑完的结果。

关键顺序是 **"代码审查在烧 GPU 之前"**：Claude 先复用你现有代码库写实验脚本（补 argparse / logging / 随机种子），然后**先**让 GPT 做一次跨模型代码审查（经验上能拦截约 80% 会浪费 8 GPU 小时的 bug），再跑最小配置 sanity check（防 OOM/NaN），最后 SSH 部署到 GPU 服务器（`screen` 里跑，捕获 stdout/stderr），由 `/monitor-experiment` 轮询到结束并收结果。

### W2 · `/auto-review-loop`（自动审稿循环 —— 招牌工作流）
> "审稿 → 修复 → 重评 → 循环，直到 ≥6/10 或轮数用尽。"

- 每轮 GPT 用**全新 thread** 冷读论文，标严重度的弱点清单；
- Claude 实施修复（改写、补 baseline、跑小实验）；**超过 4 GPU 小时的实验一律跳过**并标记人工跟进；
- 收结果、更新论文、再送审；
- `MAX_ROUNDS=4` 防死循环，达到 `POSITIVE_THRESHOLD`（默认 6/10）提前停；
- 上下文窗口满了会从 `REVIEW_STATE.json` 自动续跑；
- 明文铁律："**不许藏弱点刷分**"；
- `difficulty: nightmare` 模式下审稿人可以 `codex exec` 直接读整个仓库——Claude 无法过滤它看到的东西，是投稿前极限压测。

真实 overnight 实测（ARIS_INTRO 报告值）：5 → 6.5 → 6.8 → 7.0 → 7.5/10，共 4 轮。

### W3 · `/paper-writing`（写论文）
> 输入：`NARRATIVE_REPORT.md`（claim/实验/关键图）。输出：编译过的 LaTeX PDF。

五步流水线：`/paper-plan`（claims-evidence 矩阵 + 分节大纲）→ `/paper-figure`（JSON/CSV 自动出图出表；架构图走 `/figure-spec` 的确定性 JSON→SVG）→ `/paper-write`（分节 LaTeX；引用从 DBLP/CrossRef 拉真实 BibTeX，**绝不让 LLM 编造**）→ `/paper-compile`（latexmk 编到干净、修 overfull hbox、`pdftotext` 验页数）→ `/auto-paper-improvement-loop`（2 轮 GPT 内容评审 + 1 轮格式检查；实测 4/10 → 8.5/10）。

**投稿门**：`effort: max` 时，只有 `/proof-checker`、`/paper-claim-audit`、`/citation-audit` 三个审计全部绿灯（`tools/verify_paper_audits.sh`）才允许标"submission-ready"。

### W4 · `/rebuttal`（答辩）
> 审稿意见回来后，产出可直接粘贴进 OpenReview 的回复。

三道**安全门**（任一失败就不许 finalize，防编造）：
1. **provenance 溯源**——每句话都必须能映射到论文原文 / 审稿原文 / 用户确认过的结果；
2. **commitment 承诺**——任何"我们会补实验"式承诺必须用户批准；
3. **coverage 覆盖**——审稿人提的每条 concern 都要跟踪到回复。

流程：解析归一（按 venue 字数限制）→ 全局策略 + 逐审稿人优先级 + **封锁 claim 清单**（审稿人点了但论文撑不起来的）→（可选）证据冲刺，交接给 W1.5 补实验 → 起草 → 6 项 lint → GPT 冷读压力测试 → 双输出：`PASTE_READY.txt`（精确字符数）+ `REBUTTAL_DRAFT_rich.md`（给人改的加长版）。

### W5 · `/resubmit-pipeline`（跨会重投）
> ICML 被拒 → NeurIPS 之类。**只做靶向微改，不是重写。**

硬约束（不可覆盖）：不加新实验、不改 bib、不动框架、永不覆盖旧投稿目录。流程：物理隔离拷贝到 `<NEW_VENUE_DIR>/` → 5 层匿名检查（姓名、单位、自引、GitHub/Overleaf 链接、破坏双盲的 "we" 句式）→ `--soft-only` 审计（bib 冻结，只改正文措辞）→ YAML 白名单微编辑（`allowed_paths` / `forbidden_paths`）→ `/kill-argument` 写出最狠的 200 词拒稿备忘录并让独立裁决人逐条打分 → 编译 + 可选 Overleaf push。

### W6 · `/paper-talk`（会议报告）
> 论文中了之后：大纲 → Beamer + PPTX + 讲稿 + Q&A 准备 → 按页 Codex 评审打磨（投影字号 1.5-1.8×、字体替换目录、匿名占位纪律）→ `assurance: conference-ready` 时对幻灯片跑 claim/citation 审计，确保 slides 不引入论文撑不起来的 claim。

---

## 4. 横切机制（不在任何一条工作流里，但让系统越用越强）

### 4.1 三层（+2）审计链 —— "执行者不审判自己"

| 层 | Skill | 问的问题 | 时机 |
|---|-------|---------|------|
| 1 | `/experiment-audit` | 实验代码诚实吗？（无假 GT、无自归一化分数、无幻影结果） | 实验跑前/跑后 |
| 2 | `/result-to-claim` | 这个 claim 科学上真的由这个结果推出吗？ | 出结果后、动笔前 |
| 3 | `/paper-claim-audit` | 论文如实报告了这些数字吗？（零上下文冷读） | 投稿前 |
| +4 | `/citation-audit` | 每条 `\cite{}` 存在吗？元数据对吗？**引的论文真的支撑这句话吗？**（最有诊断价值的一条） | 投稿前 |
| +5 | `/kill-argument` | 两个新 thread 写最强 200 词拒稿备忘录 + 独立裁决 | 投稿前 |

### 4.2 审稿人独立性协议（血泪教训换来的硬规则）

每轮审稿必须是**全新 thread**，永远不用 `codex-reply` 续聊。原因：真实 NeurIPS 运行中发现续聊会把分数从 3/10 一路"哄"到 8/10——审稿人开始为自己的旧批评辩护，而不是评估当前产物。协议固化在 `skills/shared-references/reviewer-independence.md`。

### 4.3 research-wiki —— 反重复记忆

跨全部工作流的持久知识库：读过的论文、试过（含失败）的 idea、跑过的实验、验证过的 claim 全入库。下次 `/idea-creator` 起跑时先看 wiki，**失败的 pilot 变成绕行的路标**。

### 4.4 meta-optimize —— 系统自我改进的外环

读 `.aris/meta/events.jsonl` 里历史运行日志，分析"哪个 skill 常失败？哪些参数覆盖最常见？分数在哪平台期？"，据此提出 SKILL.md 改进。改进本身也要过审稿人门 + 用户批准——改系统的代码同样不许自己审自己。

---

## 5. 一张速查表：什么时候用哪个入口

| 你现在处于… | 跑这个 | 典型命令 |
|---|---|---|
| 只有一个大方向 | **W1** | `/idea-discovery "方向" --- effort: max --- sources: zotero, web` |
| 有实验计划，代码没跑起来 | **W1.5** | `/experiment-bridge --- base repo: <url>` |
| 草稿/旧论文想提分，想睡前跑 | **W2** | `/auto-review-loop "重点 3-5 节" --- difficulty: nightmare --- effort: max` |
| 有结果要成稿 | **W3** | `/paper-writing NARRATIVE_REPORT.md --- venue: ICLR --- effort: max` |
| 审稿意见回来了 | **W4** | `/rebuttal "paper/ + reviews" --- venue: ICML --- 字数上限 5000` |
| 想把论文搬到新会 | **W5** | `/resubmit-pipeline "paper/" --- venue: NeurIPS` |
| 论文中了要做报告 | **W6** | `/paper-talk "paper/" --- venue: ICLR --- assurance: conference-ready` |

两个旋钮贯穿所有工作流：
- **`effort`**：lite → max → beast（beast/max 自动启用投稿审计门）；
- **`assurance`**（独立于 effort）：draft → polished（默认）→ conference-ready（每个审计必须出 verdict 才出最终报告）。可以组合：`effort: lite + assurance: conference-ready` = 跑得快但门禁全开。

---

## 6. 给本项目（AI4AI-Harness）的对照

本项目当前用法（见 `AGENTS.md` 与 `/auto-review-loop` 约定）与 ARIS 的对应关系：

- **ZCode = 执行者**（ARIS 里的 Claude Code 位），负责写代码、跑实验、改论文；
- **Codex（经 MCP）= 跨模型审稿人**（GPT 位），review/审稿/找弱点/验收，输出沿用 ARIS 约定的 `score x/10 + verdict ∈ {ready, almost, not ready}`；
- 当前主要在用 **W2 的精神**（审稿回环）做 PROBLEM_FREE.md 冻结问题的迭代；W1/W1.5/W3 的 skill 也已装入（83 个），需要时可单独调用。

三条最值得记住的 ARIS 不变量（对任何跨模型协作都成立）：
1. 执行者与审稿人**跨家族**；
2. 审稿人**每轮新 thread**，拒绝续聊；
3. AI 分数只是**迭代信号**，不是接收概率——人类 reviewer 才是 ground truth 的近似。

---

## 7. 延伸阅读（仓库内）

- `docs/ARIS_INTRO.md` — 本文主要依据的总览（含公式化表述与真实跑分）
- `docs/SKILLS_CATALOG.md` — 82 个 skill 的完整目录
- `SETUP_GUIDE.md` / `SETUP_GUIDE_CN.md` — 安装与接入（含 9 条替代模型组合）
- `docs/CODEX_CLAUDE_REVIEW_GUIDE*.md` — 跨模型审稿回环的实操指南
- `skills/shared-references/reviewer-independence.md` — 审稿人独立性协议原文
- `aris-monitor/` — 附带的终端监控组件（跑 overnight 任务时盯状态用）
