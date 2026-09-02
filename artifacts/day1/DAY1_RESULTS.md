# Day-1 Report（8 小时窗口）— executable-harness 管线打通 + 一个重要的塌缩发现

日期：2026-08-31（09:40–17:40 窗口）　产出：`artifacts/outcomes/tthe_bird_matrix.parquet`（840 行）、`artifacts/day1/LOHO_RESULTS.json`

## 完成的工程（全部可复用资产）

1. **BIRD dev 接入**：dev.zip（346MB，11 库 1534 题）下载解压，TTHE `bird_root` 配置完成。
2. **TTHE 四个 Windows/环境 bug 修复**：claude CLI 路径解析（shutil.which）、proposer 模型传参、
   claude-CLI stdin 挂起（需写入 prompt 后关闭 stdin；已回退为管道写入）、`os.killpg` Windows 兼容。
3. **Harness population 生成**：TTHE agentic proposer（GLM-5.3-Flash via claude CLI）成功产出
   12 个 cand 文件；import-check + smoke-solve 全通过 → **population = 14 个可执行 harness**
   （bare、react、12 个 Builder 候选）。
4. **并行 outcome 收集器**（`experiment/tthe_collector.py`，6 workers）+ **LOHO 分析脚本**
   （`experiment/loho_exec.py`），统一 schema，840 行矩阵落盘。

## 关键结果：builder=target ⇒ harness 行为塌缩

| 指标 | 值 |
|---|---|
| Δ 分布（vs bare） | **0: 98.2%**，−1: 1.5%，+1: 0.4% |
| top-5 候选对 bare 错误的 union 修复率 | **0.0** |
| oracle vs best-fixed headroom | 仅 3.3pp（60 题，≈2 题的噪声量级） |
| LOHO 判定 | **无法进行**——population 无行为差异，无信号可测 |

**解释**：本次 Builder 与 Target 是同一个模型（GLM-5.3-Flash）。Builder 生成的 13 个
harness 代码各异（docstring 声称 repair loop / voting / verification 等），但逐题行为
与 bare 几乎完全一致——Builder 无法跳出它自己的默认解题策略。对照原论文设定：
**Builder 是显著强于 Target 的另一个模型**。塌缩现象本身与原论文的 headroom law
一致：harness 增益的前提是 Builder 与 Target 之间存在认知差。

这不是管线失败——管线今天全部打通了。这是一个**可解释的、可报告的科学观察**：
"AI4AI 的能力迁移需要 Builder–Target 之间的最小能力差距；同模型自建 harness 无行为多样性"。

## 对 ICLR 决策的含义

现在有两条独立的负/受限证据链：
1. **Day-0（config 级 harness）**：per-item 选择无信号（家族化、无正 offset）。
2. **Day-1（executable harness，builder=target）**：population 行为塌缩，无 per-item 互补性。

开放问题只剩一个：**builder≫target 时，executable harness 是否产生真正的 per-item 互补性？**
这是决定性实验（decisive experiment）：
- 若有 → open-set value prediction 复活，且带上独特的机制故事（迁移需要认知差）。
- 若无 → "open-set value prediction" 正式砍题；转向聚合层命题
  **"AI4AI 能力迁移需要多大的 Builder–Target 差距？"**（harness 价值 = f(能力差, 任务, 预算)），
  该问题原论文未回答，且我们已有全部工具链。

## 明天的决定性实验（半天）

1. Builder 换 DeepSeek（cc-switch 现成 profile，builder≠target 且更强），重生成 8-10 个
   harness（生成 prompt 给 5-8 个 D_A 例题而非 3 个）。
2. 重跑 outcome matrix（60-100 题 × population）。
3. 检验两个数字：(a) Δ≠0 比例是否显著上升（行为多样性）；(b) 若上升，跑 LOHO 三层判据。
4. 判定后立刻冻结论文方向并开始写作（距 ICLR 全文截止还有 25 天中的 24 天——写作时间
   仍然充足，但方向必须明天定死）。

## 遗留事项

- paratera/GLM-5.3-Flash 无 logprobs：Setting B（after-raw escalation）在 API target 上
  不可用；需要本地 Qwen（Phase C）或换支持 logprobs 的 provider。
- 60 题样本量下 headroom 判定噪声大：正式实验用 100-200 题。
- cc-switch 里还有一个 DeepSeek profile 未验证连通性。
