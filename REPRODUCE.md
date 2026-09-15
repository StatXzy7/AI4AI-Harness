# REPRODUCE — 诊断流程与验证（v2 修订，2026-09-15 第二轮）

实测平台：Windows 10 (win32)、Git Bash、Python 3.13.9（Anaconda）、numpy 2.3.5。不声称跨平台实测。
无需任何模型 API、无需 GPU；全部命令在仓库根目录执行，输出写入 `artifacts/diagnostics/<date>/<run_id>/`（每次新 run_id，不覆盖冻结历史）。

## 0. 本轮 v2 修订（响应外部复审）

方法/验证合同的修订层见 `review-stage/DIAGNOSTIC_PLAN_V2_20260915.md`；
v1.3 冻结原文保持原样。主要变化：C 类拆分为 C-rank / C-comp 两个 estimand
（恒等式 + 排列不变性）、重复身份三重门（条件字段 / 源码哈希 / 克隆矩阵）、
A 类 judge-replay 执行状态语义、BIRD 逐记录调用读取、挑战规范忠实重执行
（哈希绑定）、控制包 v2（+C9–C12）。

## 1. 冻结的方法/验证计划
- `review-stage/DIAGNOSTIC_PLAN_20260915.md`（FROZEN v1.3，历史快照，不覆盖）
- `review-stage/DIAGNOSTIC_PLAN_V2_20260915.md`（本轮修订层，**当前有效**）

## 2. 单元测试（29 项，约 16 秒；含 S3 不变量 / S1 执行状态 / 挑战执行）
```bash
python -m unittest experiment.diagnostics.test_diagnostics -v
```

## 3. 控制验证（calibration 12 控制；blinded 12 控制 + 2 规范重执行挑战）
```bash
python -m experiment.diagnostics.cli controls --phase calibration
python -m experiment.diagnostics.cli controls --phase blinded
```
预期输出（v2 控制包，六类状态 cell：A/B/C/C_comp/D/E）：
- calibration：`n_controls: 12, n_any_wrong: 0, false_support_rate: 0.0, positive_control_recognized: true`
- blinded：`n_controls: 14, n_any_wrong: 0, false_support_rate: 0.0, positive_control_recognized: true`
盲测输出绑定 `challenge_spec_sha256` 与逐模块 `code_sha256`；挑战按冻结
spec 重执行（历史 `astra_challenges_result.json` 仅作 HISTORICAL_REPLAY 溯源，
单独命令：`python -m experiment.diagnostics.cli verify-challenges --challenge-result <path>`）。

## 4. 真实存档诊断
```bash
python -m experiment.diagnostics.cli diagnose-math   # MATH-500 存档 + judge v2 重评分
python -m experiment.diagnostics.cli diagnose-bird   # BIRD phase2 18 cells
python -m experiment.diagnostics.cli inventory       # 全量 ARCHIVE_INVENTORY.csv
```
预期要点：
- MATH：A=SUPPORTED（v1 judge 重放 0 不一致）；B=SUPPORTED（320 held-out
  任务 headroom ≈5.3pp，best_fixed=bare）；C/D/E=INSUFFICIENT；
  **v2 重评翻转=14（全部为 v1 假拒绝，集中在任务 math500_split#103；
  历史"0 翻转"产物不可由已提交代码复现，已更正论文表述）**。
- BIRD：18 cells × 4 臂 B 全 SUPPORTED；A=REFUTED（重复键；judge replay
  如实标注 not_executed）；C/D/E=INSUFFICIENT；逐记录调用已读取
  （core 子集 288,104 次 logical calls）。

## 5. 汇总交付（v2 本轮 run 目录）
- `artifacts/diagnostics/20260915/20260915_controls_46d54a63/`（calibration v2）
- `artifacts/diagnostics/20260915/20260915_controls_4c4b4a3b/`（blinded v2，
  含 challenge_execution 哈希绑定块）
- `artifacts/diagnostics/20260915/20260915_diagnose_math_57a1616d/`
  （含更新版 DECISION_IMPACT.csv：追加 3 行复审驱动修正）
- `artifacts/diagnostics/20260915/20260915_diagnose_bird_300d3dcf/`
- `artifacts/diagnostics/20260915/20260915_verify_challenges_0130d65c/`
  （HISTORICAL_REPLAY 报告）
- `CLAIM_LEDGER.json`：追加 C-10（14-flip 更正主张）

## 6. 审核记录
- 外部复审（本轮修订输入）：Codex 独立审稿 2026-09-15（4/10，意见全文见会话记录）
- 冒烟：`review-stage/astra_20260915/smoke_record.json`（gpt-6-astra/xhigh，codex exec 0.154.0，文件事实核对）
- 计划审核 3 轮 + 挑战契约 + 冷启动终审：`review-stage/astra_20260915/*_last_message.txt` 与 `*_events.jsonl`（JSONL 事件日志）
- 线索核验：`review-stage/VERIFICATION_20260915.md`（7 条线索逐项复现）

## 7. 论文
```bash
cd paper/latex && pdflatex main && bibtex main && pdflatex main && pdflatex main
```
本轮改动：
- 新增主文第 6 节 `sec_diagnostics.tex`（诊断方法进正文 + H_stable 恒等式
  Eq.(1) + 排列/占优/互补不变量 + 哈希绑定验证摘要 + 14-flip 自审更正）；
- 标题改为 *Diagnosing Apparent Complementarity in AI-Generated Harness
  Populations*；摘要与引言贡献列表同步；
- `sec_crossdomain.tex`：唯一向量口径改为 33/36（含 bare）/32/35（仅生成
  成员）；"changed none" 更正为 14 flips；
- `sec_appendix.tex`：app:diagnostics 按 v2 语义重写；附录承接移动内容
  （Phase-I 协议探针小节、provider acquisition 段、phenomenon 图、
  same-core 分解表 tab:decomp、R2 细节补全）；
- 正文经压缩后（Intro→Conclusion）完整落在 9 页内（当前构建正文止于第 9 页，
  AI use statement 不计入）。

## 注意
- `codex exec` 需 @openai/codex ≥0.154.0 才支持 `-m gpt-6-astra`；npm 包名是 `@openai/codex` 而非 `codex`。
- 所有随机性固定种子；`hash()` 不用于任何种子派生（用 SHA256）。
- 若运行结果与上文"预期要点"不符，视为阻断项，不要调整阈值后继续。
- 历史运行目录（含 v1 控制验证与旧 DECISION_IMPACT）一律保留为冻结历史，
  不覆盖、不删除。
