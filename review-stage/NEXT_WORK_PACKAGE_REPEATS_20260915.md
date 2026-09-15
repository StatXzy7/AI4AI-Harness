# 下一工作包：真实证据缺口实验（2026-09-15 立，源自 recheck5）

背景：诊断管线 v2 的代码/合同层已经过五轮独立复审收敛（recheck5：四项代码
blocker 全部确认修复，measurement correctness 8/10，42/42 测试）。当前唯一
的 not-ready 来源是**真实存档上的实验证据缺口**（research-contribution 维度）。
本文档把 recheck5 列出的缺口转为可执行的实验工作包；全部需要模型 API 预算，
不属于离线诊断范围。

## WP-1 同条件独立重复（最高优先，解锁 C 类）

- **缺口**：MATH-500 存档只有单一执行条件（repeat 0 / cache on），C-rank 与
  C-comp 在真实存档上永远 INSUFFICIENT。
- **实验**：对 MATH-500 的 35 个成员 × 400 eval 任务，在**冻结源码哈希**
  （与 repeat 0 完全一致）下补采 R≥3 次独立执行（同 target、temperature 0、
  同 judge）。已有 R2/R3 管线（`experiment/revision/`）可复用。
- **验收**：`diagnose-math` 的 C 类（ranking 与 complementarity）首次在真实
  存档上产生非弃权判定；同时验证重复独立性门（无克隆矩阵告警）。
- **预算估计**：~28k 次逻辑调用（35×400×2 次新增重复）。

## WP-2 held-out selector 效用验证（解锁 D/E 类）

- **缺口**：BIRD 存档无 dev/eval 执行切分，pi_Z 不可训练；MATH 无独立重复。
- **实验**：在 WP-1 的新执行存档上划分 dev/eval（沿用 frozen dev=first-80
  口径或预注册新切分），运行完整 D/E 判定，并补一个 M1b 对照（dev-fixed +
  bare fallback + 成本匹配）。
- **验收**：真实存档上 D/E 首次产生 SUPPORTED/REFUTED 判定，或以受控方式
  弃权并给出最小缺失证据；M2 vs M1b 判定矩阵落盘 CONTROL_VALIDATION。

## WP-3 桥接实验（隔离 verification 与策略空间限制）

- **缺口**：Phase-II 的 gate 同时排除了两类允许的策略变换，D−A 对比不能
  解释为纯 verification 效应。
- **实验**：最小桥接——仅对被 gate 排除的两个 prompt 变换（hint_guard、
  format_guard）补测"neutral validity + 强制保留该机制"的臂，与现有四臂
  可比。具体设计需先过一轮预注册审核。
- **验收**：verification-only 对照臂落盘，Phase-II 结论更新或确认。

## WP-4 独立验证集（可选，增强外部效度）

- **缺口**：现有控制验证全部来自机制导出的合成控制；缺一个未参与方法
  设计的独立执行存档。
- **实验**：选定公开的 LLM 执行轨迹数据集（或新采一个小规模跨域群体），
  在冻结方法版本（绑定当前 code SHA）上跑完整 A–E，前瞻性记录判定。
- **验收**：CLAIM_LEDGER 增加"前瞻性验证"条目；回顾性标签不再覆盖全部
  证据。

## 执行顺序与预算

WP-1 → WP-2（串行，WP-2 依赖 WP-1 的重复数据）；WP-3、WP-4 可并行。
预计总预算以 logical calls 计：WP-1 ~28k、WP-2 复用无新增生成、WP-3 视
设计 ~5–10k、WP-4 视数据源。全部实验沿用现有账本/审计基础设施
（`artifacts/` 分目录、writer.lock、manifest 哈希绑定）。

## 复审锚点

recheck5（`review-stage/codex_recheck_20260915/recheck5_last_message.txt`）
"Research evidence remains incomplete" 一节即本工作包的验收对照清单；
WP 全部完成后提请第六轮独立复审。
