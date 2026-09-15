# REAL_EVIDENCE_PROTOCOL_V1 — 真实证据采集前瞻冻结（2026-09-15）

状态：**FROZEN v1.0**（G0 审查通过前不得启动任何付费采集；通过后按本文件执行，
不得回改。修订必须追加章节并带时间戳，不覆盖历史记录。）
范围：本轮新采集实验（WP-1R/WP-2R），不覆盖、不改判任何历史工作包、
v2 诊断合同或 `NEXT_WORK_PACKAGE_REPEATS_20260915.md` 中的 WP-1..4 原文。

## 0. 冻结的 estimand 与比较对象

- **E1（C-rank，真实重复）**：真实成员面板在 400 eval 任务上、R=3 个全新
  执行轮次下，成员排序的重复稳定性（诊断 v2 §1 的恒等式 + 排列不变性判定）。
- **E2（C-comp，同代码对照）**：plug-in 任务条件互补优势（有限重复选择下
  再现的优势），对照 9 个同代码 bare 采样槽位构成的 exchangeable null。
  **验收 = 对照链完整**；不预设真实池 null 检验通过与否的结论。
- **E3（D，selector 效用）**：冻结执行前特征 policy π_Z 相对 dev-fixed 的
  逐任务配对差异（5 折 CV，训练折内特征），eval 400 上评估。
- **E4（E，预算内核算）**：π_Z / M1b / dev-fixed / bare 的实际 logical calls、
  token usage、成本与 harm；E_1（budget_by_construction）不适用于本面板
  （成员调用 >1），另立 E_b（统一上限 b）为独立命名 estimand。
- 比较对象（固定）：bare、dev-fixed、预固定随机选择（种子冻结）、M1b、
  π_Z、oracle（描述性上限，非可部署收益）、best-fixed。
  oracle / self-consistency / 执行前 router 三者不可混称。

## 1. 成员口径（manifest 为准）

- 总体 36 = 35 生成成员 + bare（`experiment/gsm8k/agents/`，与存档 code_hash
  LF 归一化后一致，2026-09-15 核验记录于 CURRENT_RUN_MANIFEST §C）。
- **本轮实际采集面板 P = 8 生成成员 + bare = 9 成员**，结论限定到该面板，
  不声称全体 35 生成成员都得到验证。
- 选择规则（先冻结后抽签，不使用任何 eval/正确性数据）：
  - 资格：冻结 repeat-0 存档 `n_llm_calls` 每成员均值 ≤ 3.05（纯成本属性，
    用于预算可行性；该筛选使面板偏向低调用机制，**如实披露为预算约束
    面板，不是 35 成员的均匀样本**）→ 21 个合格成员（glm 1 / qwen 3 /
    deepseek 6 / kimi 2 / minimax 6 / ernie 3）。
  - 抽签：salt=`wp1r-panel-v1-20260915`；每 builder 按最小
    SHA256(salt|stratum|member) 取 1 席（6 席），其余合格成员按最小
    SHA256(salt|atlarge|member) 取 2 席；bare 固定入组。
  - 抽签结果（已落盘 `review-stage/WP1R_PANEL_DRAW.json`）：
    gsm_deepseek_s0_g3、gsm_ernie_s0_g3、gsm_glm_s0_g6、gsm_kimi_s0_g3、
    gsm_kimi_s0_g4、gsm_minimax_s0_g0、gsm_minimax_s0_g3、gsm_qwen_s0_g5 + bare。
- best-fixed / dev-fixed / oracle 均在本面板 9 成员内定义。

## 2. 重复口径

- **R=3 个全新执行轮次**（repeat id 1/2/3），每轮全部 9 成员 × 400 eval
  任务完整执行；重复身份 = 新 condition ID + 新 run 身份 + 独立调度时间块。
- 历史 repeat-0（cache-on、旧采集批次）**不计为同条件重复**，仅作历史参照。
- 旧存档任何数据不得计入本轮分母；新旧矩阵合并仅允许显式标注
  `mixed_condition` 的敏感性分析，不进主分析。
- R=5 或改变 R 的任何设计：必须在**看到任何正式结果之前**决定并重新计费；
  解封后禁止扩样。

## 3. 独立性口径

- 结果矩阵完全相同 ≠ 复制/非独立证明；结果不同 ≠ 统计独立证明。
- 克隆矩阵一致性仅作为**触发器**：命中即触发来源核验（request ID、
  服务端响应 ID、时间戳、响应哈希），人工归档核验结论后再决定是否
  将该 cell 标记为来源可疑；不得仅凭结果相同自动拒绝或自动接受。
- 9 个 bare 同代码槽位（clone-c1..c9）与面板内 bare 成员：**代码相同是设计
  事实**，其执行独立性只能由"每次执行独立发起请求、无共享缓存、独立时间
  调度"的过程证据支持，报告为 separately-initiated same-code executions，
  不得表述为"已证明统计独立"。
- 同代码 null（E2）使用 clone 槽位的 exchangeable null 分布，属诊断对照，
  不冒充真实人群效应。

## 4. 稳定互补性判定规则（防选择偏差）

- 有限 R 的重复均值再取 max 存在系统性正偏；**plug-in headroom>0 或
  bootstrap 下界>0 不构成稳定互补性成立**。
- 判定链（全部满足才可表述"证据支持"级措辞，否则 INSUFFICIENT/NEGATIVE）：
  1. 真实池 plug-in 任务条件优势显著大于 clone-pool null 分布（预设 δ=1.0pp，
     单侧置换检验，任务级配对）；
  2. 同一优势在独立验证轮（发现轮=repeat 1；验证轮=repeat 2–3，映射冻结后
     只评估）中再现（主判定），3 次重复轮转（副判定）方向一致；
  3. C-rank 恒等式与排列不变量在真实数据上非弃权。
- 允许的统计方法修订：需先经 reviewer 审核并作为 v1.x 追加，前瞻生效。

## 5. 验收目标（防"必须非弃权"）

- 验收对象：**采集→来源→统计→主张链的完整性**（分母保全、状态账本、
  provenance 哈希、分析可复现、结论不越权）。
- C/D/E 判定为 SUPPORTED / REFUTED / INSUFFICIENT 均可接受；
  **不因结果方向、p 值大小或弃权而重跑、扩样或修改规则**。

## 6. 预算口径与账本

- 一次 harness execution ≠ 一次底层调用；所有成员内部多轮调用、生成、
  验证、重试全部经统一 budgeted client（复用 `fresh_runtime.py` 的
  RunStore / ResourceBudget / AuditedTransport），每层记账：
  experiment_run > harness_execution > logical_call > provider_attempt。
- 停用 SDK 自动重试（max_retries=0）；429/5xx 状态重试 ≤2 次/逻辑调用，
  每次重试记 `status_retry` 事件；unknown/失败保留预留不按零计。
- **请求前原子预留**：每 cell 最坏 logical calls + max_output_tokens +
  request bytes；超限先记 `resource_budget_rejected` 再拒绝发送。
- 状态机：PLANNED → RESERVED → SENT → SUCCEEDED / FAILED_KNOWN /
  UNKNOWN_REMOTE / NEVER_STARTED / SEALED。
- 禁止本地 response replay；供应商前缀/prompt 缓存与完整响应复用分别记录。
- 预算上限：
  - 投影 logical calls ≈ 38,044（real pool 21,795 + clone 10,800 + dev 5,449），
    硬上限 **45,000 provider attempts**（先触及即停）；
  - 总成本 ≤ **MAX_TOTAL_COST_CNY = 4000**：pilot 实测 unit 成本后冻结投影，
    若 95% 投影成本 > 4000 CNY，暂停并报告，等待作者决定；
  - 并发 2→4，每逻辑调用重试 ≤2。
- 成本记录：每次 HTTP 记 usage（prompt/completion tokens）+ request ID；
  定价以供应商可核验来源为准，无法核验时以"token 计数 + 定价未知"报告，
  不虚构金额。

## 7. 任务总体与数据切分

- **固定 400 个既有 eval 任务**（`artifacts/gsm8k_audit/math500_split.json`
  的后 400 条）+ **100 dev 任务**（前 100 条）；split SHA256 冻结。
- 泛化口径：对已分析过的 400 任务重新执行/切分，**不得描述为全新未见任务
  验证**；WP-2R 结果标注为"回顾性任务 + 前瞻执行"。
- WP-2R 泄漏控制：同题重复不跨训练/验证折；dev-accuracy 特征仅由训练折
  计算；只用执行前可获特征（题目文本、冻结机制类别、训练折内 dev-acc）；
  禁用答案、正确性、eval-derived 难度、执行后轨迹、judge 结果。

## 8. 执行条件（condition ID 冻结）

- model：`GLM-5.3-Flash`（requested model id；返回别名仅记录，不声称
  权重等同历史批次；backend 无法核验时记录该限制）。
- endpoint：`https://llmapi.paratera.com/v1`（以冒烟核验为准）。
- temperature 0.0（与冻结存档同条件）、max_tokens 32000、thinking_style none、
  **cache off**（每次逻辑调用真实发送）、judge = 已提交版 `is_correct`
  （数值/latex 归一化比较，绑定源码哈希）。
- 固定 seed 策略：不使用 per-request seed（端点支持性待核验）；采样多样性
  来自 provider 非确定性（历史 14.5% bare 翻转证明其存在）；**禁止解封后换 seed**。
- 调度：按 repeat → 时间块 → 成员交错（SHA256 固定序），成员/轮次/时间
  均衡分布；不通过语义 nonce 制造差异。
- WP-3R 桥接（如获准另批）：gate 结果不得改变生成预算、候选身份或任务；
  共同候选池 + 固定八策略词表 + P0/PS/PV/PSV 臂；PV−P0、PSV−PS 及交互；
  结论限定该池与协议；新增两臂不自动隔离 verification，需共同接口与
  固定策略空间的政策比较表述。**本轮先冻结设计草案，执行另批**。

## 9. 缺失、失败与停止规则

- 中断恢复按唯一键（cell=repeat×member×task）续跑，不重启整轮；
  已 SENT 但结果未知的请求保留 UNKNOWN_REMOTE，对账后决定是否重试。
- **允许暂停的条件**：预算硬上限触及；provider 连续故障（滑动 200 cell
  内 >15% FAILED_KNOWN/UNKNOWN）；身份冲突（源码/配置哈希漂移）；
  基础设施异常。全部暂停必须落盘快照 + 报告。
- **禁止的停止/扩展依据**：p 值、准确率、效应方向、审稿分数、成员表现。
- 停止后分母保全：所有 NEVER_STARTED/UNKNOWN 列入报告，不填零。

## 10. 最小有意义效应与统计

- δ = 1.0 pp（headroom 与 selector 优势）；CI 与检验的抽样层级 = 任务
  （重复轮配对 bootstrap / 置换）；不把重复数当独立任务样本。
- 多重性：主终点（E2 主判定）1 项；E1/E3/E4 及轮转副判定按 Holm 校正；
  未显著 ≠ 等效；H=0 不证明总体无互补。
- 分母：完整记录 SUCCEEDED/FAILED/UNKNOWN/NEVER_STARTED；主分析用完整
  案例 + 保守成功率双报；敏感性界并列。

## 11. 允许与禁止的结论

- **允许**：在本面板、本条件、本任务集上，报告实测 oracle/best-fixed/bare/
  headroom、C-rank/C-comp 判定（含弃权）、selector 配对差异、真实调用与
  成本、clone-null 对照结果。
- **禁止**：推广到全体 35 成员或未见任务；声称可部署收益/生产 router；
  用 plug-in 数字冒充稳定互补性；把 clone 槽位说成独立人群；把旧 repeat-0
  计入同条件重复；改写历史 D−A 数字；宣称已证明统计独立。

## 12. WP-2R 设计细节（冻结）

- 候选池 = 面板 P（9 成员）；5 折 CV（任务级，种子 20260915，同题重复
  同折）；折内模型平均（非 stacking）；π_Z 特征 = 题目文本 TF 特征 +
  训练折内各成员 dev-acc（held-out 折标签不进特征）；tie-break = 成员 ID
  字典序；fallback = bare。
- M1b = dev-fixed + bare fallback + 完整性检查（不弱化基线）。
- E_b：统一上限 b=3 logical calls/任务，实际调用、token、成本、harm 全报。
- λ=1 harm 惩罚沿用 v2 合同，明确是额外惩罚项而非概率解释。

## 13. 交付物清单（本轮）

协议与偏差记录、预算授权与账本、无秘密 endpoint 审计、task/member/
condition/split manifests、逐请求逐执行状态与来源索引、冻结 policy/CV/
特征来源、repeat/clone 对照报告、控制验证记录、DECISION_IMPACT 与
CLAIM_EVIDENCE 增补、Codex 审查原始记录（argv/JSONL/哈希）、自动生成的
论文数字/表/图、REPRODUCE 增补、fresh build 日志与 source/PDF 哈希、
CHECKPOINT / NEXT_ACTION。

## 修订记录

- v1.0（2026-09-15）：首版冻结（ZCode，G0 审查前）。
- v1.1（2026-09-15，G0 首轮 4.5/10 后的预采集修订，逐条对应 G0 阻断 1–7）：

### A1. 温度语义（G0-1）
§8"temperature 0.0"更正为：**采样温度由各成员冻结源码内的 `self.llm(...)` 调用
决定**（bare=0.0；部分成员按自身机制使用非零温度，如 self-consistency 的 0.4）。
这与 repeat-0 存档走完全相同的代码路径（harness 请求温度 → solver 直传）；
`bridge.temp_override` 全程不使用。成员源码哈希即绑定其逐调用温度条件。
每条 execution 记录实际 transmitted temperature（AuditedTransport 请求体留痕）。

### A2. 全局 attempt/cost 账本（G0-2）
- 新增 `GlobalBudget`（`fresh_collect_math.py`）：跨进程文件锁原子预留，
  所有 shard 与 worker 的每次 HTTP 请求先预留 1 个 provider attempt，
  总上限 45,000（先触及即停，预留不退还——unknown 不按零计）。
- 成本：每请求 usage 已由 AuditedTransport 落账；`dollar_cost` 保持 None
  直至定价核验。**pilot 完成后、正式采集前**：以 pilot 实测 token/请求分布
  的 p95 与供应商可核验单价（如可得）冻结成本投影；若 95% 投影总成本
  > 4000 CNY，正式采集不启动并报告作者。定价不可核验时，以
  "token 账本 + 单价未知"交付，不虚构金额。
- 重试（每逻辑调用 ≤2 次 status retry）同样经 GlobalBudget 计数——
  attempt 上限对重试生效。

### A3. clone 成员加载（G0-3）
所有成员（含 clone-c1..c9）统一从 manifest 的 `source` 路径加载：在
`gsm8k.agents` 包内以唯一模块名 `gsm8k.agents._iso_<digest>` 执行源文件，
成员 ID（身份）与源码哈希（条件）分离；clone 槽位与面板 bare 共享同一
bare.py 源码哈希，分别独立发起执行。共享源码哈希在 manifest 中显式记录。

### A4. 并发与失败政策（G0-4）
- 父进程 worker 池并发 = 2 起步，配置允许 1..4（授权范围）；成员 n>1
  采样请求可能瞬时超过并发数（HTTP 层），attempt 总账本仍然封顶。
- 失败政策（冻结）：请求全部闭合的 harness/执行失败 → 父级以
  `error` 结果落盘（official_correct=None），计入滑动失败窗口
  （窗口 200 cell，失败率 > 0.15 即停）；存在 unknown/drain_expired/
  budget_rejected 请求 → 立即停止采集并快照，等待对账；
  worker 生命周期无法结算（wall_timeout 且无闭合请求）→ 停止。
  恢复按 cell 键续跑；unfinished cell 存在时 RunStore 拒绝复用（对账前置）。

### A5. 统计检验完整规格（G0-5）
- 主判定（E2）：H0：真实池任务条件优势 ≤ δ=1.0pp；H1：> δ。
  统计量 = 验证轮（repeat 2–3）上逐任务条件优势的均值，减去 clone-null
  同一统计量的均值。检验：任务级配对置换检验（对任务内成员-槽位配对
  标签翻转，10,000 次置换，种子 20260915），单侧 α=0.05；同时报告
  95% bootstrap CI（任务重采样，重复轮配对），**CI 下界 > δ 与置换
  p<α 同时满足才判 SUPPORTED**。
- clone-null 构造：9 个 clone 槽位按与真实池完全相同的发现/验证流程
  （发现轮=repeat 1 选每任务槽位，验证轮=repeat 2–3 评估冻结映射）
  计算同一统计量；null 分布来自槽位身份的置换（10,000 次）。
- 发现/验证映射：发现轮=repeat 1；映射冻结后仅在验证轮评估。3 轮
  轮转（每轮轮换发现角色）作为副判定，主判定只报告预注册轮次划分。
- 缺失 cell 规则：主分析要求任务 × 成员 × 全部 R 轮完整；缺任一轮的
  任务从主分析剔除并列清单（保守分母）；敏感性：以任务内可用轮均值
  插补重算，双报。
- 多重性：主判定 1 项不校正；E1（C-rank）、E3（selector）、E4（E_b）
  与轮转副判定共 4 项族，Holm 校正后报告。
- 未显著 ≠ 等效；clone-null 覆盖下的结论限定为"在该面板与该 null 口径下"。

### A6. 面板绑定（G0-6）
- 采集 manifest 记录 `panel_draw`（panel、eligible、salt、
  `WP1R_PANEL_DRAW.json` 的 SHA256）；`prepare()` 校验配置成员与抽签
  文件完全一致；`CURRENT_RUN_EVIDENCE_SHA256.json` 增补抽签文件哈希。
- 资格披露更正：repeat-0 `n_llm_calls` 由成员对响应的运行时控制流决定
  （并非完全独立于输出的外部属性），该资格规则定性为**历史成本口径
  资格**，非无偏均匀抽样；面板结论限定与 §1 披露一致。

### A7. 唯一正式执行器与命令（G0-7）
- 唯一正式 MATH 采集器：`python -m experiment.revision.fresh_collect_math
  --config <frozen config>`（cache off、audited transport、GlobalBudget、
  repeat 1/2/3、400 eval 任务、dev 独立 config）。
- `experiment/gsm8k/collect.py` 仅作 repeat-0 存档复现/历史参照，
  **不得**作为本轮正式采集执行器；其 docstring 的容差表述与
  `is_correct` 精确数值相等实现不符，以代码为准并已在 REPRODUCE.md 更正。
- 判定语义披露：存档口径 `official_correct` 为归一化字符串精确比较
  （非数值容差判分）；新旧数据统一用同一提交版函数，哈希绑定。
