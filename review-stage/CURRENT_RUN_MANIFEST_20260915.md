# CURRENT_RUN_MANIFEST — 真实证据轮（2026-09-15 启动）

- 分支：`research/wp1r-real-evidence`（自 main `62c1a2fd501cb8ae6889f5373dd7ccbcfaa8ac77` 切出）
- 远程：origin/main = 62c1a2f（本轮启动时与本地一致）
- 工作树：启动时**无已跟踪文件修改**；未跟踪文件仅为历史 artifacts
  （ledger.sqlite / writer.lock / raw 目录等，全部保留，不删除）。
- 执行者：ZCode（GLM-5.3-Flash 会话）；审核者：Codex exec（gpt-6-astra / xhigh / read-only）。
- 证据哈希索引：`review-stage/CURRENT_RUN_EVIDENCE_SHA256.json`（权威文件 SHA256；
  一律按显式路径选取，禁止按目录时间戳 / 文件名排序 / glob 末项选择"最新结果"）。

## 四态分离

### A. 工程已修复（已提交，代码层）
- 诊断管线 v2（`experiment/diagnostics/`）：C-rank/C-comp 拆分、重复身份三重门、
  E 预算门（拒绝 NaN/None/bool/list/超支）、CV 方向修复、typed condition identity。
- ε=0.15 正式修订：`DIAGNOSTIC_PLAN_V2_20260915.md` §12（commit 21d9726），
  recheck5 阻断 1 已在文档层解决（尚待 recheck6 形式确认）。
- 测试：42/42（`python -m unittest experiment.diagnostics.test_diagnostics`，
  recheck5 独立复跑确认；本轮启动另重跑一次并记录）。

### B. 报告称已验证（recheck5 已核验的工件，但 recheck5 未全部重跑）
- MATH 诊断 `20260915_diagnose_math_245a88fd`：A/B 不变、C/D/E=INSUFFICIENT、
  14 次 judge-v2 翻转保留。
- 控制验证（recheck5 指认的最新时间戳目录）：blinded `20260915_controls_3e879330`、
  calibration `20260915_controls_dc218f5b`，零 mismatch。
- BIRD：18 cells × B 全 SUPPORTED；A=REFUTED；C/D/E=INSUFFICIENT。

### C. 本轮实际重跑（本轮新产生的实测）
- 启动时成员源码核验：36 个成员源码（35 生成 + bare）与存档 code_hash
  在 **LF 归一化后全部一致**；磁盘 CRLF 仅为 checkout 行尾转换，不构成源码变更。
  （原始字节哈希不同；新采集 manifest 同时记录 raw 与 normalized 两种哈希。）
- 42 项单元测试本轮重跑：见 CHECKPOINT（启动后第一条记录）。
- 其余本轮结果以 `artifacts/wp1r_20260915*/` 与后续 CHECKPOINT 为准。

### D. 科学证据仍缺失（本轮目标，非代码缺陷）
- MATH：无同条件独立重复 → C-rank/C-comp 在真实数据上无判定。
- D/E：无任务留出 selector 效用证据（BIRD 无 dev/eval 执行切分；MATH 无重复）。
- 无隔离 verification 的政策桥接实验（WP-3R）。
- 无未参与方法设计的前瞻验证存档（WP-4R）。
- 上述即 recheck5 "Research evidence remains incomplete" 全部范围，本轮按
  REAL_EVIDENCE_PROTOCOL_V1.md 逐项补足；**不承诺全部变为 SUPPORTED**，
  验收对象是采集-来源-统计-主张链完整性。

## recheck5 NOT_EXECUTED 范围（本轮须知）
1. Fresh CLI regeneration（diagnose/controls 重跑）——recheck5 仅检查既有工件；
2. pytest 未成功执行（环境无可用临时目录）——本轮以 unittest 为准并记录；
3. PDF 重建未执行——仅检查既有 PDF/log；本轮 G4 前必须重建并哈希。

## 环境
- Python 3.13.9 (Anaconda)，numpy 2.3.5；平台 Windows 10 / Git Bash。
- 科研 API：origin `https://llmapi.paratera.com`（历史采集使用 `/v1` 路径，
  `external/TTHE/config.yaml` base_url=`https://llmapi.paratera.com/v1`，
  solver_model=`GLM-5.3-Flash`）；凭证经 `experiment/.env_tthe` /
  `experiment/.env_tthe_ziyang` 中的 `PARATERA_API_KEY` 提供（两把不同 25 字符
  key，均不在 shell 环境中）。**本轮只报告"已配置"，不打印、不入 Git、不传 reviewer。**
- Codex CLI 0.154.0（`@openai/codex`），gpt-6-astra 可用性已由
  `review-stage/astra_20260915/smoke_record.json` 证明。
- ARIS skills：项目清单 `.aris/installed-skills.txt`（83 项，junction 至
  `Auto-claude-code-research-in-sleep/skills/`）；本轮复用 auto-review-loop 的
  Codex exec 调用约定；不升级 ARIS，不改动 junction。
