# REPRODUCE — 诊断流程与验证（2026-09-15 本轮）

实测平台：Windows 10 (win32)、Git Bash、Python 3.13.9（Anaconda）、numpy 2.3.5。不声称跨平台实测。
无需任何模型 API、无需 GPU；全部命令在仓库根目录执行，输出写入 `artifacts/diagnostics/<date>/<run_id>/`（每次新 run_id，不覆盖冻结历史）。

## 1. 冻结的方法/验证计划
`review-stage/DIAGNOSTIC_PLAN_20260915.md`（FROZEN v1.3，经 3 轮 gpt-6-astra/xhigh 审核）。

## 2. 单元测试（13 项，约 12 秒）
```bash
python -m unittest experiment.diagnostics.test_diagnostics -v
```

## 3. 控制验证（calibration + blinded，各 8 控制）
```bash
python -m experiment.diagnostics.cli controls --phase calibration
python -m experiment.diagnostics.cli controls --phase blinded
```
预期输出：`n_any_wrong: 0, false_support_rate: 0.0, positive_control_recognized: true`（两阶段同）。
产出：`control_manifest_*.json`（含 SHA256）、`control_validation_*.json`。

## 4. 真实存档诊断
```bash
python -m experiment.diagnostics.cli diagnose-math   # MATH-500 存档 + judge v2 重评分
python -m experiment.diagnostics.cli diagnose-bird   # BIRD phase2 18 cells
python -m experiment.diagnostics.cli inventory       # 全量 ARCHIVE_INVENTORY.csv
```
预期要点：MATH A=SUPPORTED（judge 重放 0 不一致）、B=SUPPORTED（headroom ≈5.3pp，best_fixed=bare）、C/D/E=INSUFFICIENT、v2 翻转=0；BIRD 18 cells × 4 臂 B 全 SUPPORTED、C/D/E=INSUFFICIENT。

## 5. 汇总交付（本轮已生成，位置按最新 run 目录）
- `artifacts/diagnostics/20260915/…/CONTROL_VALIDATION.json`（两阶段指标 + M0–M3 对比）
- `…/DECISION_IMPACT.csv`（13 案例决策影响记录）
- `…/CLAIM_EVIDENCE.json`（8 条主张-证据-状态-边界）
- `…/astra_challenges_result.json` + `review-stage/astra_20260915/challenge_spec.sha256`（盲挑战预提交哈希）
- `…/ARCHIVE_INVENTORY.csv`（math500 14,400 行 + bird_phase2 182,400 行）

## 6. 审核记录
- 冒烟：`review-stage/astra_20260915/smoke_record.json`（gpt-6-astra/xhigh，codex exec 0.154.0，文件事实核对）
- 计划审核 3 轮 + 挑战契约 + 冷启动终审：`review-stage/astra_20260915/*_last_message.txt` 与 `*_events.jsonl`（JSONL 事件日志）
- 线索核验：`review-stage/VERIFICATION_20260915.md`（7 条线索逐项复现）

## 7. 论文
```bash
cd paper/latex && latexmk -pdf -interaction=nonstopmode main_revision_20260915_insight.tex
```
本轮改动：`sec_crossdomain.tex`（K_eff→同口径唯一向量数、union-all-fail 命名、0.68–0.915、判分 v2 零翻转引用）、`sec_appendix.tex`（新增 app:diagnostics 附录）。

## 注意
- `codex exec` 需 @openai/codex ≥0.154.0 才支持 `-m gpt-6-astra`；npm 包名是 `@openai/codex` 而非 `codex`。
- 所有随机性固定种子；`hash()` 不用于任何种子派生（用 SHA256）。
- 若运行结果与上文"预期要点"不符，视为阻断项，不要调整阈值后继续。
