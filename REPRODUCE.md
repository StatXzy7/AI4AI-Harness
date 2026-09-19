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

## 2. 单元测试（42 项，约 43 秒；含 S3 不变量 / S1 执行状态 / E 预算门边界 / CV 方向性参考实现 / 挑战执行）
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
（第二轮复审修复后：blinded `20260915_controls_d3a32145` 与 calibration
  `20260915_controls_e721360b` 重跑全对 [目录名与阶段以此为准]；第三轮
  复审修复后另有最新重跑，以时间戳最新目录为准。每轮运行均绑定
  spec+code SHA256。）
- `artifacts/diagnostics/20260915/20260915_diagnose_math_57a1616d/`
  （含更新版 DECISION_IMPACT.csv：追加 3 行复审驱动修正；最新重跑为
  `20260915_diagnose_math_245a88fd`，状态一致）
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

## 8. WP-1R/WP-2R 真实证据轮（2026-09-15 至 2026-09-19）

预冻结协议：`review-stage/REAL_EVIDENCE_PROTOCOL_V1.md`（v1.0-v1.3 修订
全部带时间戳，附录 `sec_app_wp1r.tex` 披露完整修订史）。采集、封存与
分析全程经 Codex（gpt-6-astra/xhigh）独立审查：G0 四轮（终轮 8.8/10
ready）、G2/G3 三轮（终轮 8.7/10 almost）、G4 见 `review-stage/
codex_g4_20260919/`。

### 采集（需 PARATERA_API_KEY 环境变量，来自 experiment/.env_tthe）
```bash
# 冻结配置生成（无秘密）
python -m experiment.revision.wp1r_configs
# 各臂采集（cache off、audited transport、GlobalBudget 60000 attempts）
python -m experiment.revision.fresh_collect_math --config artifacts/wp1r_20260915/configs/eval_real_cont2.json
python -m experiment.revision.fresh_collect_math --config artifacts/wp1r_20260915/configs/eval_clone_cont.json
python -m experiment.revision.fresh_collect_math --config artifacts/wp1r_20260915/configs/dev_real_cont2.json
# 中断恢复：先对账再重启（unknown_remote 不自动重试）
python -m experiment.revision.reconcile_cell --arm eval_real_cont2
```

### 封存与分析（离线，无 API）
```bash
python -m experiment.revision.wp1r_seal --merged --arms eval_real,eval_clone,dev_real
python -m experiment.revision.wp1r_analysis          # E1/E2 + A8.6 + E4
python -m experiment.revision.wp2r_selector          # E3（需 dev + eval 臂）
python -m experiment.revision.wp1r_render            # 生成论文宏与策略表
```

### 结果要点（如实）
- E1 C-rank: **SUPPORTED**（bare 稳定优于多数生成成员）；
  C-comp: INSUFFICIENT（6 个三轮全缺失 cell，清单在 analysis_report）。
- A8.6 主判定: **INSUFFICIENT**（覆盖率门：真实臂排除 12.5% > 10%）；
  数值上 A_real=0.14pp vs A_clone=0.13pp，D=0.15pp ≪ δ=1pp，p=0.998。
- clone 臂 plug-in H_stable=2.67pp：有限重复下 plug-in max 可显著为正，
  不能作为稳定互补性证据（真实 H_stable 不可识别）。
- E3: π_Z 全任务弃权，与 dev-fixed=bare 打平 94.96%；随机成员 -10.12pp。
- E4: 50,817 attempts / 79.8M tokens / 保守成本上界 ¥2,656 < 4000。
- 论文数字全部由 `wp1r_render.py` 生成的宏（wp1r_numbers.tex）注入，
  禁止手改。
