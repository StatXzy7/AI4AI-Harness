# Day-0 Reproduction Report — fragility-grid (arXiv 2608.21382)

日期：2026-08-31　执行者：自动化 pilot（见 `experiment/day0_sanity.py`）

## 数据与许可

| 项 | 值 |
|---|---|
| 仓库 | `external/fragility-grid`（NikolaTesla-007/fragility-grid，MIT License，© 2026 V.S. Raghu Parupudi） |
| 数据位置 | `results/fragility/records/`，48 个 JSONL（每 benchmark × model 一个文件） |
| 模型数 | 12（Qwen3 / Llama 3.x / Gemma4 / Mixtral 家族，3B–70B） |
| harness 配置数 | 26 = generation × {letter_plain, letter_paren, digit_labels, instruction} × 6 种选项排列 (2) + loglikelihood × {cloze_plain, cloze_question} |
| item 数 | 3,679（ARC、HellaSwag、MMLU、TruthfulQA） |
| correctness 字段 | `bits` dict：每 config 一个 0/1 correctness bit |
| confidence 类字段 | `ll_margin`（raw model top-2 likelihood margin，**属于 Setting B after-raw 特征**）、`n_gen_unparsed` |
| 额外字段 | `question` 原文（可用于 task 文本特征）、`gold` 选项索引 |
| 参照配置 | `gen|letter_plain|p0`（legend `_meta.ref_config`，即标准 MCQ 评测方式） |

## 复现执行

原命令 `python repro/fragility_analysis.py` 直接运行失败：`repro/common.py:17` 顶层
`import torch`（torch 仅用于 GPU 重跑路径与种子设置）。处理方式：以 torch stub
（`artifacts/day0/torch_stub/`）绕过 import，未修改原仓库任何文件；figures 输出重定向到
`artifacts/day0/repro_out/`，`analysis.json` 写回仓库内（确定性 seed=1234，可再生成）。

结果：**复现成功**。关键数字与论文一致：

| 指标 | 论文 | 本地复现 |
|---|---|---|
| corr(discrimination, fragility) | 0.28, CI [0.25, 0.30] | 0.277, CI [0.251, 0.302] |
| 排名由 config 决定（rank-#1 模型数） | 4 / 12 | 4 / 12（champion 分析一致） |
| config-lucky / accuracy band | 每模型分数是一个区间 | `per_model` 一致输出 |

## 对本项目的适用性说明

- 这里的 "harness" 是 **config 级**（prompt 格式 / 选项顺序 / 打分模式），不是 executable
  agent harness。Experiment A 只用于验证 value-prediction 数学形式的可学性（sanity），
  不作为论文主实验。
- `ll_margin` 是模型对该 item 的原始置信度：放入预测器即构成 **Setting B (after-raw)**；
  Setting A (pure pre-execution) 必须排除。两者在 `day0_sanity.py` 中分开报告。
- 选项排列语义（已从 `repro/fragility_grid.py` 核实）：`shown[p] = opts[perm[p]]`，
  因此 gold 在展示中的位置 = `perm.index(gold)`——这是 (item × config) 可在执行前算出的
  合法交叉特征。
