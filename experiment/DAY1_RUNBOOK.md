# 72h Pilot Runbook v2（Day 0 = 08-31 晚 / Day 1 = 09-01）

> v2 变更：**API-first，本地部署移出关键路径**。Day 1 不再配 WSL2 + vLLM。
> 目标不变：9 月 3 日晚对 PROBLEM_FREEZE.md §5 三层 kill criteria 做书面判定。

## 产出物（pilot 唯一交付）

`experiment/results/outcome_matrix.parquet`，每行一条记录：

```
benchmark | split | item_id | target_model | harness_id | y_harness (0/1) | y_raw (0/1) |
delta (-1/0/+1) | raw_logprob_feats | harness_meta(builder, seed, sha256) | tokens_in | tokens_out
```

## Day 0（今晚，零 API 成本）

**Fragility-grid LOHO sanity（Experiment A）**——在花一分钱之前回答"数学形式可学吗"：

1. `cd external/fragility-grid && pip install numpy scipy matplotlib && python repro/fragility_analysis.py`
   复现论文数字，确认数据管线理解正确（CPU 秒级）。
2. 加载 `results/fragility/records/`（每题 26 个 correctness bit + top-2 margin），
   构造 Δ 矩阵：以每个 (model, config) 对的 majority config 为伪 raw 基线，
   Δ ∈ {−1,0,+1}。
3. 跑两个 sanity 实验：
   - closed-set：训练 configs H1-H20 的 value predictor（特征：item 文本 embedding +
     config legend 特征 + margin），在 H1-H20 内 held-out items 上测；
   - **LOHO**：train H1-H20 → test H21-H26（unseen config）。
4. 记录 AUC / harm reduction。**这只是可学性 sanity，不达预期不等于杀题**
   （config 级 harness 的结构差异远小于 executable harness），但达预期是强心剂。

## Day 1（09-01）

1. **TTHE 跑通**（Windows 直接 Python 即可，不需要 WSL——demo 离线无沙箱依赖）：
   ```bash
   cd external/TTHE && pip install -r requirements.txt
   cp config.example.yaml config.yaml   # 填入 OpenAI-compatible base_url + api_key_env
   PYTHONPATH=. python -m text_to_sql.optimize --db demo --cap 5 --max-rounds 3
   ```
   验收标准：demo 跑通、runs/ 里有 per-item 结果。**今天的目标是第一个
   task × harness outcome，不是部署模型。**
2. **选两个 API target**：一个 cheap/mid（如 deepseek-chat 档）+ 一个 stronger；
   确认 logprobs 支持情况并记录（不支持则 after-raw escalation 用替代置信度特征，
   如 verbalized confidence / 采样一致性，写明局限）。
3. **Builder 生成 harness 种群**：写 Builder prompt（只准看 D_A 的 5%，
   输出 TTHE `HarnessBase` 子类 Python 文件 + 50 词描述），2 builder × 3 seeds 起，
   目标 8-12 个。存 `experiment/harnesses/{builder}_{seed}.py`，sha256 存档冻结。
   注：也可收割 TTHE optimize 循环各 branch 的 harness 作为种群补充。

## Day 2（09-02）

1. 全 harness × D_B∪C∪D 样本 × 2 API target 跑完 outcome matrix。
   BIRD 用 TTHE 的 bird loader（需下载 BIRD dev，注意 dev_databases 路径配置）。
2. 计算并记录：L1 oracle gap、L2 task-only router（embedding+LR，5-fold on D_B）、
   P(Δ=+1)/P(Δ=−1) 每 (harness, target) 格、互补性热图；
   baseline：confidence gate、majority vote（high-cost）、SC@K（cost-matched）。
3. 第一个 LOHO 试跑（不调参，只验证管线）：5 harness 训练 value predictor，
   held-out 第 6 个测 AUC / harm reduction。

## Day 3（09-03）

1. 按 §5 判定 L1/L2/L3，写入 `experiment/KILL_DECISION.md`。
2. GO → 冻结 predictor 设计，进入正式实验；Pivot/Kill → 按 §9 止损转 ICML 2027。

## 纪律（不变）

- D_D 不进 pilot 任何统计；pilot 统计只用 D_B/D_C。
- 每个 harness 文件带 sha256；评测日志存档。
- API 消耗逐日记录 `experiment/api_ledger.md`；Builder 会话全部落盘。
- 本地 5090（vLLM + Qwen3 family）推迟到 Phase C：cross-model 泛化 + 干净
  logprobs 轴，只在核心结论成立后启动。
