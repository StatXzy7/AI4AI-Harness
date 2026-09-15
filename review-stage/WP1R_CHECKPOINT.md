# WP-1R CHECKPOINT（滚动更新，最新在最下）

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
