# WP-1R CHECKPOINT（滚动更新，最新在最下）

## 2026-09-16 采集中的事件与政策
- **eval_clone 第一次 stop-and-reconcile**（协议规定的正确行为）：
  cell `clone-c1 × math500_split#481`（repeat 1）发生 SDK 120s ReadTimeout，
  provider 完成状态未知 → 父级立即停止并快照。已用
  `experiment/revision/reconcile_cell.py` 按冻结政策对账：该 cell 记为
  `unknown_remote`（official_correct=None，attempt 保留计账，tokens 未知
  → 保守成本按臂均摊计价），**不重试该请求、不填零**。对账后采集恢复。
  该任务在 A8.6 完整案例规则下将被剔除并列缺失清单。
- `PARATERA_API_KEY` 不跨后台 shell 持久 → supervisor（`supervisor.sh`）
  统一从 `experiment/.env_tthe` 读取并守护双臂；单 unknown 事件自动对账，
  不自动重试 HTTP；预算守卫 44,500。
- 分析模块合成烟测通过；正式分析待 3 轮完整（当前 repeat 1 进行中）。


## 2026-09-16 启动
- G0：4 轮独立审查（4.5 → 5.5 → 6.5 → **8.8/10 ready**），全部记录在
  `review-stage/codex_g0_20260915/`（argv、JSONL、意见、快照哈希）。
- G1：provider 冒烟 PASS（/models 200 + GLM-5.3-Flash 在列 + 参数/usage
  完整 + 无 secret 泄漏）；正式 pilot 3/3 SUCCEEDED（走正式采集器）；
  预算门 v1.3 冻结（`review-stage/WP1R_BUDGET_GATE_V1_3.md`）：
  token 账本 × 断点价 44.3 CNY/1M（保守上界闭合 4000 CNY）。
- **正式采集已启动**：eval_real（9 成员 × 400 eval 任务 × repeats 1–3，
  约 21.8k 逻辑调用），共享全局账本 45,000 attempts（pilot 已用 3）。
- 监控状态（启动后 ~5 分钟）：18 cells 完成、15 正确、0 错误事件、
  预算 reserved=52。运行速率与延迟符合预期（per-exec 中位 ~33s）。
- 分支 `research/wp1r-real-evidence` 已推送至 origin（G0/G1 工件已含）。

## 恢复说明
- 采集器按 cell 键续跑：中断后重新执行同一条命令即从断点继续，
  已完成 cell 跳过；存在 unfinished cell（unknown 请求）时 RunStore
  拒绝启动，需先对账（设计如此，不自动重试 unknown）。
- 监控命令：
  `python -c "import sqlite3;c=sqlite3.connect('artifacts/wp1r_20260915/eval_real/ledger.sqlite');print(c.execute(\"SELECT COUNT(*),SUM(json_extract(result,'$.official_correct')) FROM tasks WHERE result IS NOT NULL\").fetchone())"`
  `cat artifacts/wp1r_20260915/global_budget.json`

## 2026-09-16 A9-resume：延续迁移（重要事件）
- **根因**：RunStore manifest 绑定启动时的协议文件哈希与采集器源码哈希；
  A9 预算修订 + GlobalBudget 修复使 byte-identical 重启不可能，双臂停摆 ~2h。
- **处置（审计路径）**：`migrate_ledger.py` 创建延续账本
  `eval_real_cont` / `eval_clone_cont`（新 manifest 绑定 A9 后协议与当前
  源码哈希、60,000 上限），把旧账本全部已完成 cell（1590 + 4167）的结果
  与全部事件逐条复制并重映射 cell 键，附 `ledger_migration` 事件（含源
  账本 SHA256 绑定）。旧账本原样保留为冻结证据。
- **config 恢复说明**：eval_real/eval_clone 旧 config 的
  max_provider_attempts 恢复为 45000（manifest 创建身份）；实际执行上限
  由共享状态文件（60,000）决定（GlobalBudget 现允许 state ≥ manifest）。
  延续臂与 dev_real 使用 60,000。
- **对账政策扩展**：reconcile_cell 三分规则——(1) 无 logical_start 事件
  → 清除行（NEVER_STARTED，无请求发出、无预算消耗）；(2) 请求全闭合但
  worker 死亡 → failed_known（attempts 计账）；(3) http_unknown →
  unknown_remote（原有）。

## 2026-09-19 WP-1R 采集完成 + 封存 + 正式分析结果

### 采集与封存
- eval_real_cont2: **10800/10800 SEALED**（SUCCEEDED 主导；unknown_remote 128、
  failed 146 = 2.5% 缺失，走 A8.6 完整案例规则）；eval_clone_cont:
  **10800/10800 SEALED**（unknown 26、failed 34 = 0.6%）。run_invalid=0。
- 每臂以其 manifest 绑定的采集器字节做封存校验（cont2 绑 49c25a6 版、
  clone_cont 绑 63a1347 版）；漂移披露：fresh_collect_math.py 在采集后
  有分析期修订（工作树版本已恢复，git 历史保留绑定字节）。

### 预算终账（E4）
- 总计 logical calls 32,592 / http attempts 42,294 / 已知 tokens 67.3M；
  **保守成本上界 ¥2,982 < 4000 CNY**（断点价 33.3/1M 口径）。

### 正式分析结果（如实）
1. **E1 C-rank: SUPPORTED** —— 面板内存在稳定的成员排序差；方向：bare
   显著优于多数生成成员（如 bare − deepseek_g3 = 25.7pp、bare − ernie_g3 =
   18.4pp，CI 均不含 0）。
2. **C-comp（v2 机器）：INSUFFICIENT** —— 6 个 (member,task) cell 三轮全部
   缺失，H_stable 不可识别；缺失清单已列。
3. **A8.6 主判定（clone-null 对照）：NOT SUPPORTED（阴性）** ——
   A_real = 0.14pp、A_clone_obs = 0.13pp、D = 0.15pp ≪ δ = 1pp；
   置换 p = 0.998；D 的 95% CI = [-0.89, +1.18]pp。
   **发现轮选择的"任务条件优势"与同代码噪声不可区分。**
4. **clone 臂的 plug-in headroom = 2.67pp（H_stable，CI [1.7, 3.8]）**
   ——9 个同代码 bare 槽位仅凭有限重复取 max 就产生 2.7pp 的"表观互补"，
   为 C-06 的诊断提供了直接实证：plug-in oracle-headroom 主要是选择偏差。
5. 结论：真实面板的 headroom 基本可由同代码重复噪声解释；与论文的
   "apparent complementarity" 主线一致——不是正收益，而是对既有主张的
   诚实量化。

### 未竟
- WP-2R dev 采集（dev_real，~5.4k calls）与 E3 selector 分析：预算与
  attempts 仍够（46,310/60,000），待本轮审阅后决定是否继续。
