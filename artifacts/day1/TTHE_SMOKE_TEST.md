# TTHE Smoke Test Report — 2026-08-31

## 运行环境

- 无 GPU、无本地模型部署。**provider: mock**（TTHE 自带离线管线验证模式）。
- `config.yaml` 由 `config.example.yaml` 改 provider 而来；真 API 只需改回
  `provider: openai` + base_url + `api_key_env` 环境变量（**尚未接入付费 key**，
  当前所有 correctness=0 是 mock 故意返回错误 SQL 的预期行为，只验证管线）。

## C1 冒烟结果

命令：`PYTHONPATH=. python -m text_to_sql.optimize --db demo --cap 3 --max-rounds 3 --fresh --run-name smoke_mock`

| 验收项（PROBLEM_FREEZE §指令八） | 结果 |
|---|---|
| raw/bare harness 可执行 | ✅ |
| react harness 可执行 | ✅ |
| proposer 生成新 harness | ✅（生成 18 个 cand_*.py；mock 下 branch 逻辑回退到 bare 属预期） |
| harness code 持久化 | ✅ `agents/cand_smoke_mock_*.py`，18 个文件 |
| per-execution 记录（task/harness/model/output/correctness/latency） | ✅ 收集器实测 |
| task × harness × model outcome records | ✅ 60 行 parquet |

## Harness population 注册表（§九）

`artifacts/outcomes/harness_registry.jsonl`：21 个 harness（bare、react、18 cand_*），
每个含 harness_id / code_path / code_hash(sha256) / description。
TTHE 原生把每个 branch 的候选写为独立 .py——**winner-only 修改量比预期小**：
文件已全量落盘，只需注册表（本次已补）+ lineage 解析（后续从
`logs/<run>/branch_log` 回填 parent_id 与 generation_round）。

## 统一 outcome schema（§十）

`artifacts/outcomes/tthe_smoke.parquet`：60 行 × 18 列，
schema = `dataset, domain, task_id, model_id, harness_id, baseline_harness_id,
baseline_correct, harness_correct, delta, task_text, harness_text, harness_description,
prompt_tokens, completion_tokens, latency_ms, cost_usd, split, error`。
✅ 与冻结 schema 一致。token 用量暂为 None：ase/llm.py 未透出 usage，
接入真 API 后在 `_complete` 处加 usage 捕获（单点修改）。

## 样例 outcome（outcome_sample.parquet 即 tthe_smoke.parquet）

```
dataset=demo domain=text_to_sql task_id=demo#0 model_id=deepseek-chat
harness_id=bare baseline_correct=0 harness_correct=0 delta=0 latency_ms=12
```

## 工程问题与解决

1. demo 数据集只有 3 道题，`--cap 5` 越界 → 改 `--cap 3`。
2. config.yaml 是 YAML 非 JSON，收集器改用正则读 solver_model。
3. mock provider 需要 `OPENAI_API_KEY` 环境变量存在（任意占位值即可）。

## 是否可以扩规模

**可以。** 接入真 API 后按 §十一 扩展：
5–10 tasks × 3–6 harnesses × 1 target → 50–100 tasks × 6–10 harnesses × 2 targets。
需要的 API key 到位前的阻塞项：仅此一项。

## 待接真 API 后的第一批动作

1. `config.yaml`: provider=openai，base_url/api_key_env 填入（key 只走环境变量）。
2. `PYTHONPATH=. python -m text_to_sql.optimize --db demo --cap 3 --max-rounds 3` 验证
   真实 branch 推进 + proposer 质量。
3. 下载 BIRD dev，跑 `tthe_collector.py --db <bird_db> --limit 50`。
4. Builder prompt 生成差异化 harness 种群（D_A 5% 规则见 PROBLEM_FREEZE §3）。
