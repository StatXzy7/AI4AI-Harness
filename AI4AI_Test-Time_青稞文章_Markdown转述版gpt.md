# 当 Harness 也能被 AI 自动设计：AI4AI 正在重写小模型变强的方式

> **来源**：青稞社区  
> **发布日期**：2026-08-31  
> **原文**：https://qingkeai.online/blog/AI4AI@Test-Time  
> **相关论文**：https://arxiv.org/pdf/2608.12307  
> **主题**：AI4AI / Strong-to-Weak Scaffolding / Harness / Test-Time Scaling  
>
> **说明**：本文档是对原网页正文的干净 Markdown 化整理与详细转述，去除了导航、登录、分享、阅读量、上一篇、订阅、社区介绍等网页噪声；不是原文的逐字转载。

---

## 核心观点

AI 系统的能力不再只由模型参数决定。进入 Agent 时代后，模型外部的 **Harness / Scaffolding**——包括任务拆解、工具调用、状态管理、记忆、规则、程序化求解器、验证器以及上下文组织方式——正在成为决定最终系统能力的重要部分。

Salesforce AI 与 UIUC 的这项工作提出 **Strong-to-Weak Scaffolding**：

- 强模型不直接替弱模型完成测试题；
- 强模型作为 **Builder AI**，在测试前为较弱的 **Target AI** 自动设计一套 Harness；
- Target 模型参数保持不变；
- Builder 的能力以 Prompt、程序、规则、路由、状态表示和验证流程等形式被“外置”；
- 最终目标是让较弱模型依靠更好的系统结构完成原本难以完成的任务。

这是一种典型的 **AI4AI at Test-Time**：AI 不仅解决任务，也开始设计另一个 AI 的工作环境。

---

## 关键结果

以 **GPT-5.4-mini** 作为 Target AI 时：

| 设置 | 四个任务平均准确率 |
|---|---:|
| GPT-5.4-mini 裸模型 | 0.488 |
| 自动 Harness 平均表现 | 0.763 |
| 自动 Harness 最佳表现 | 0.912 |
| GPT-5.4 裸模型 | 0.619 |
| 人工设计 UserHarness | 0.939 |

其他重要观察：

- 针对 GPT-5.4-mini 的 **57 次** Harness 自动构建实验全部优于裸模型基线。
- 一共进行了 **72 次**独立构建实验。
- 11 种 Builder 配置全部获得平均正收益。
- Harness 中由代码、规则和确定性流程直接承担的工作比例，与最终准确率呈较强正相关，约 **r = 0.72**。
- 单纯增加代码量与性能的相关性很弱，约 **r = 0.22**。
- Harness 最终效果与 Builder 的 refinement 次数相关性很低，约 **r = 0.17**。
- 不同 Target × Benchmark 条件下，Target 原始性能留下的提升空间与 Harness 收益相关性约为 **r = 0.75**。

这些结果说明，提升并不主要来自“让模型再多想几遍”，而是来自更合理地重新分配认知工作。

---

# 一、强模型不替弱模型答题，而是替它改“系统”

实验里有两个核心角色：

### Target AI

真正执行隐藏测试集任务的模型。

### Builder AI

能力更强的模型，负责在正式测试之前设计 Target 的运行系统。

Builder 可以在可编程环境中：

- 修改 Prompt；
- 编写 Python 程序；
- 加入规则；
- 维护显式状态；
- 增加任务分类和 Routing；
- 对输入进行结构化；
- 对输出进行格式约束；
- 实现答案检查与验证；
- 对某些存在稳定算法的子问题直接采用确定性求解。

因此，优化对象不是模型参数，而是**模型解决问题的过程**。

## 数据约束

对于每个 Benchmark：

- Builder 只能访问随机抽取的 **5% 样本**作为 Validation Set；
- Builder 根据这些样本分析 Target 的失败模式并迭代 Harness；
- Harness 开发结束后被冻结；
- 最终直接运行在 Builder 从未看到的 Hidden Test Set 上。

所以 Builder 需要解决的是一个元问题：

> 识别哪些失败必须依赖模型能力解决，哪些失败实际上可以通过程序、状态、规则、路由或验证机制消除。

Strong-to-Weak Scaffolding 的重点因此不是让强模型代做，而是让强模型学会**怎样组织弱模型工作**。

---

# 二、为什么选择 Theory of Mind 任务？

论文没有只使用普通数学或知识问答，而选择 **Theory of Mind（ToM，心智理论）**，因为这类任务同时包含两类认知过程。

## 容易程序化的部分

例如：

- 谁看见了什么；
- 谁在什么时候离开；
- 某个物体被谁移动；
- 某个角色当前掌握哪些事实。

这些信息可以转化为显式状态，并由程序持续更新。

## 难以完全程序化的部分

例如：

- 一个角色相信什么；
- 某个角色存在怎样的错误信念；
- A 如何理解 B 的信念；
- 多层 belief recursion；
- 对话、行为与社会意图推断；
- Bayesian goal inference。

因此 ToM 很适合研究一个核心问题：

> 当 Harness 帮助模型时，究竟是哪一部分“思考”被系统接管了？

## 四个 Benchmark

实验覆盖：

1. **BigToM**
2. **Hi-ToM**
3. **MMToM-QA**
4. **MuMA-ToM**

这些 Benchmark 涉及：

- belief tracking；
- recursive mental states；
- 对话和行为理解；
- Bayesian goal inference。

Builder 在 Cursor、Claude Code、GPT Codex 等 Agentic Coding Environment 中自动探索 Harness 设计。

研究还分析了：

- Builder 模型本身的强弱；
- Validation Budget；
- Coding Environment；
- 不同 Harness 技巧的可复用性；
- 不同 Target 是否需要不同 Scaffold；
- 性能提升时“认知负担”究竟被转移到了哪里。

---

# 三、Harness 的收益甚至可能超过直接换更强模型

一个非常重要的结果是：

> 在某些任务上，升级整个推理系统，比单纯换成更大的模型更有效。

GPT-5.4-mini：

- 裸模型平均准确率：**0.488**
- 自动 Harness 平均：**0.763**
- 最佳自动 Harness：**0.912**

而更强的 GPT-5.4 在裸跑状态下：

- 平均准确率：**0.619**

这意味着：

**“较弱模型 + 优秀 Harness” 可以超过 “较强模型 + 裸运行”。**

而且这种提升具有较好的稳定性：

- 57 次针对 GPT-5.4-mini 的 Scaffold Run 全部超过 baseline；
- 11 种 Builder Configuration 都产生平均正增益。

不过自动 Harness 尚未超过最好的人工系统：

- 最佳自动 Harness：**0.912**
- 人工 UserHarness：**0.939**

因此一个值得继续研究的问题是：

- 人类 Harness 设计者还掌握哪些自动 Builder 没有发现的结构？
- 这些设计模式是否也能进一步自动化？

---

# 四、哪些认知工作应该从模型内部搬到 Harness？

## 发现 1：优秀 Harness 不是简单让弱模型“思考更久”

最直观的方法可能是：

- 写更长的 Prompt；
- 增加 Chain-of-Thought；
- 多采样；
- 让模型反复自检。

但论文发现，更稳定的增益通常来自系统工程层面的结构。

常见方法包括：

- Answer format constraints；
- Greedy decoding；
- Task routing；
- Structured input/output。

而表现更好的 Harness 往往进一步采用：

- Deterministic solver；
- Structured extraction；
- Polarity logic；
- Explicit state tracking。

核心思想是：

如果一个步骤具有稳定、确定的结构，就不必每次都让概率模型重新推理。

例如：

- 数值或逻辑计算交给程序；
- 角色状态交给显式状态机；
- 稳定任务类型先分类再 Routing；
- 输出结构通过 schema 或 parser 固定；
- 可以确定检查的条件交给 verifier。

### 相关性结果

- 外部代码和规则实际承担的任务比例 vs. 最终准确率：**r ≈ 0.72**
- 单纯代码量 vs. 最终准确率：**r ≈ 0.22**

因此关键并不是“写更多代码”，而是：

**把适合确定性计算的认知负担真正从模型身上拿走。**

---

## 发现 2：迁移的更像“认知结构”，而不是模型参数或答案

传统 Knowledge Distillation 通常希望把 Teacher 的能力压进 Student 的参数。

Strong-to-Weak Scaffolding 不同：

- Target 参数没有更新；
- Builder 也不直接提供隐藏测试答案；
- Builder 最终留下的是可执行的外部结构。

这些结构可能包括：

- 分类器；
- 规则；
- 状态表示；
- 程序；
- Routing；
- Prompt 模板；
- 约束；
- Validator；
- 工作流。

因此，被迁移的是 Builder 对“这个任务应该如何解决”的认识。

可以把它理解为一种 **Cognitive-Load Reduction**：

1. 一部分任务彻底 Offload 给确定性程序；
2. 剩余需要 LLM 推理的部分被拆成更小、更清晰的子任务；
3. Target 只处理最适合语言模型处理的部分。

从系统角度看，这类似于给弱模型增加一个“认知外骨骼”。

---

## 发现 3：并不是所有推理都能轻易编译成规则

不同 Benchmark 中，可被 Harness 固化成程序化流程的比例差异很大。

| Benchmark | 大致可由固化 Harness 工作流处理的比例 |
|---|---:|
| BigToM | 约 94% |
| Hi-ToM | 约 51% |
| MuMA-ToM | 约 36% |

BigToM 中大量信息属于稳定的状态追踪，因此很适合程序化。

到了更复杂的任务：

- belief recursion 更深；
- 对话更开放；
- 社会推理更复杂；
- Bayesian goal inference 更困难。

此时，仅靠增加程序逻辑已经无法完全替代模型理解。

这表明 AI 推理困难至少可以拆成两类：

### A. 组织与计算的不可靠

适合 Harness 化：

- 状态追踪；
- 约束；
- 算术；
- 稳定逻辑；
- 格式；
- Routing；
- Verification。

### B. 问题本身需要真正理解

例如：

- 深层递归信念；
- 开放语境中的社会理解；
- 模糊意图；
- 高阶 Bayesian inference。

这类能力仍然主要取决于模型本身。

因此，未来 Harness 的关键问题并不是“能否用代码替代推理”，而是：

**如何自动判断某个认知步骤究竟应该交给模型，还是应该编译成程序、状态、工具或规则。**

---

## 发现 4：Builder 的价值主要来自理解任务结构，而不是反复试错

Builder 可以不断：

- 修改 Harness；
- 重新运行 Validation；
- 查看反馈；
- 再 refinement。

直觉上，尝试次数越多，系统应该越强。

但论文观察到：

- Hidden Test 表现与 Validation 最佳成绩高度相关；
- 与总 refinement 次数相关性只有 **r ≈ 0.17**。

相反，当固定 Builder 为 **Opus-4.7**，提高 Builder 的 Reasoning Effort 时，生成 Harness 的质量持续提升。

这说明优秀 Builder 的优势可能主要来自：

- 更快发现任务规律；
- 更准确地区分可程序化部分和不可程序化部分；
- 更好地设计任务分解；
- 更合理地把认知工作分配给 LLM、程序和 verifier。

从计算资源分配的角度看，这提供了另一种 Test-Time Scaling 思路：

- 与其让便宜 Target 在每一次调用时重复昂贵推理；
- 不如让强 Builder 在开发阶段进行一次较昂贵的“元推理”；
- 然后把结果固化成可以被重复执行的 Harness。

---

## 发现 5：越弱的 Target，通常越能从 Harness 中获益

论文还将 Target 更换为能力更强的 **Gemini-3.5-flash**。

结果显示一个明显规律：

> Target 原始性能留下的 Headroom 越大，Harness 往往越容易产生明显增益。

不同 Target × Benchmark 条件下：

- Headroom 与 Harness 提升的相关性约为 **r = 0.75**。

对于 GPT-5.4-mini：

- 很多 Builder 能带来 0.2、0.3 甚至更高的提升。

对于本来已经擅长某些任务的强 Target：

- Harness 收益明显变小；
- 个别任务甚至会轻微下降。

原因很直观：

Harness 是一种帮助，也是一种约束。

当模型不足以独立完成任务时：

- 流程化、Routing、状态管理和验证器能够明显降低认知负担。

但如果模型已经能很好解决任务：

- 过度复杂的固定流程可能限制模型自由发挥。

因此更理想的 Harness 应该具备**模型自适应能力**：

- 判断 Target 哪些能力不足；
- 只在必要位置介入；
- 在模型足够可靠的地方减少约束。

---

# 五、AI4AI 的真正变化：Scaling 开始走出模型

现代 Agent 系统并不是裸模型，而是一个复合系统，通常包括：

- Model
- Memory
- Tools
- Router
- Verification
- Skills
- Context Management
- Programmatic Logic
- State
- Retrieval
- Execution Environment

因此未来衡量 AI 能力时，可能需要区分：

## Model Capability

模型单独运行时的能力。

## System Capability

模型被放入一个优化良好的 Harness 后，整个系统最终能够达到的能力。

论文中的典型例子是：

- Model Capability：**0.488**
- System Capability：最高达到 **0.912**

这意味着 Scaling 未必只发生在模型参数内部。

---

## 强模型可能成为 Builder，而不是每次都亲自执行任务

一种潜在架构是：

### 开发阶段

昂贵的强模型负责：

1. 分析任务结构；
2. 分析弱模型失败模式；
3. 设计 Prompt；
4. 编写工具；
5. 创建规则；
6. 构建状态管理；
7. 设计验证机制；
8. 自动搜索 Harness。

### 部署阶段

廉价、小型 Target 模型负责：

- 高频执行；
- 处理 Harness 已经简化过的任务；
- 只对真正需要语言推理的部分调用模型能力。

于是昂贵推理成本可以从：

> 每一次 inference 都支付

转变为：

> Builder 阶段支付一次，然后在大量后续执行中复用。

这是一种非常重要的 AI 系统经济学变化。

---

# 六、从这篇工作可以抽象出的 AI4AI 研究框架

这项工作可以被概括为如下流程：

```text
Strong Builder AI
        │
        ▼
Observe Target AI failures
        │
        ▼
Infer task structure
        │
        ├── What should remain LLM reasoning?
        ├── What can become deterministic code?
        ├── What should become explicit state?
        ├── What should be routed?
        └── What can be verified automatically?
        │
        ▼
Generate / modify Harness
        │
        ▼
Validation feedback
        │
        ▼
Refine Harness
        │
        ▼
Freeze Harness
        │
        ▼
Weak / Cheap Target AI
        │
        ▼
Hidden Test / Production Tasks
```

优化对象发生了变化：

```text
传统路线：
Data + Compute + Training
        ↓
Model Parameters
        ↓
Better Model

AI4AI / Harness 路线：
Strong AI + Validation Feedback
        ↓
Prompt / Code / Tools / Rules / State / Verification
        ↓
Better AI System
```

---

# 七、这项工作的研究意义

## 1. Test-Time Scaling 不一定等于更多 Token

传统 Test-Time Scaling 经常意味着：

- 更长 CoT；
- 更多 sampling；
- self-consistency；
- tree search；
- verifier-guided search。

这篇工作展示了另一种路线：

**把一次性的高成本 reasoning 编译成可长期复用的系统结构。**

---

## 2. Harness 本身可能成为新的自动优化对象

过去 AutoML 优化：

- architecture；
- hyperparameters；
- training pipeline。

未来 AI4AI 可以自动优化：

- system prompt；
- task decomposition；
- tool selection；
- routing；
- memory；
- state representation；
- verifier；
- deterministic solver；
- context policy；
- Agent workflow。

---

## 3. Strong-to-Weak 的能力迁移不再只有蒸馏

传统 Strong-to-Weak：

```text
Strong Model
    ↓
Training Data / Preference / Distillation
    ↓
Weak Model Parameters
```

Harness 路线：

```text
Strong Model
    ↓
Executable Cognitive Structure
    ↓
Weak Model + External System
```

它不要求重新训练模型，因此更适合：

- 闭源 API 模型；
- 快速迭代；
- 小预算实验；
- 频繁变化的任务；
- 企业 Agent；
- 大规模低成本部署。

---

## 4. 模型与 Harness 可能形成 Co-evolution

未来可能出现循环：

```text
Better Builder Model
      ↓
Better Harness
      ↓
Stronger System Performance
      ↓
More difficult tasks / better feedback
      ↓
Better Harness-search strategies
      ↓
...
```

因此，AI Scaling 的一个重要方向可能从：

**只优化模型**

逐渐变成：

**模型 + Harness + Environment 的共同优化。**

---

# 八、值得继续研究的问题

基于论文结论，可以自然延伸出以下研究问题：

1. **Harness Search**
   - 如何自动搜索 Prompt、代码、Tool、Router 和 Verifier 的组合？

2. **Adaptive Harness**
   - 是否可以针对不同模型能力动态调整 Scaffold 强度？

3. **Generalization**
   - 在少量 Validation 数据上设计出的 Harness 能否跨数据集、跨任务泛化？

4. **Overfitting**
   - Builder 会不会对 Validation Set 过拟合？

5. **Harness Transfer**
   - 一个模型上搜索出的 Harness 能否迁移给另一个模型？

6. **Harness Distillation**
   - 能否把人工专家 Harness 反向蒸馏成 Builder AI 的训练数据？

7. **Meta-Harness**
   - 是否可以设计一个通用系统，让 Builder 自动决定需要哪些外部模块？

8. **Cost-aware AI4AI**
   - 如何同时优化准确率、Token 成本、延迟和 Builder 搜索开销？

9. **Long-Horizon Agent**
   - 在软件工程、Web Agent、Research Agent 等长程任务中，Harness 是否比单纯增强基础模型更重要？

10. **Self-Evolving Harness**
    - Harness 是否可以根据线上失败案例持续自动修改自身？

---

# 九、一句话总结

这项工作的核心不是“强模型教会弱模型答案”，而是：

**强模型先理解任务，再把自己的解题方法转化成 Prompt、程序、状态、规则和验证流程，从而让较弱模型依靠一个更聪明的外部系统完成任务。**

从这个视角看，下一阶段 AI Scaling 的重要战场可能不只是模型参数，而是：

**谁能够自动设计出更好的 Harness。**
