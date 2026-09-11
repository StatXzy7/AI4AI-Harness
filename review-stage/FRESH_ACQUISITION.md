# Fresh 采集开发版：已实现的修复与正式实验余项

2026-09-10。上一阶段是诊断，本阶段新增可执行的采集版本 `fresh_collect.py` / `fresh_runtime.py`。旧 collector、缓存、历史结果及两版论文均保留。

**限定开发实现 ready；完整 formal runtime 和 A–D 仍 not ready。** 不能通过排除当前尚不能安全处理的 harness 缩小原 A 的种群，也不能把本机 HTTP 请求当作提供方统计独立性的证明。

## 当前实现

- 用 SQLite 逐事件提交请求账本，采集目录同时只允许一个写进程。manifest 绑定 acquisition、repeat 计划、harness 身份和顺序、任务清单、数据库、协议文件、源码、模型请求设置及包版本。同目录条件变化明确报错，完成行按整个运行身份恢复。
- 每个 cell 创建新的 solver，任务身份不可换绑；harness 的已 join 线程共享当前任务，模型多样本线程分别记录 sample 身份。所有请求直接到提供方客户端，无应用层响应缓存。
- SDK 隐式重试、HTTP 重定向及环境代理关闭。显式 HTTP 状态重试由 manifest 记录；连接/读取失败保留 unknown，不自动重新请求。没有旧客户端的额外超时后台线程池。
- HTTP transport 记录每次尝试的实际发送内容、状态、响应 ID、request ID、原始 JSON 响应及 usage。逻辑调用数、请求样本数、HTTP 尝试数分别统计；缺失 usage 使总 tokens 保持 null，同时单列已知 tokens。金额始终为 null，不能由 fixture tokens 推算预算或账单。
- 可选的 `resource_budget` 绑定到 manifest，并在每个 cell 的 provider 请求发出前限制逻辑调用数、请求样本数、请求体字节数和请求的最大输出 token 额度。超限请求写入 `resource_budget_rejected` 并停止该 cell；账本同时记录已保留的输出 token 与请求体字节预算。该合同提供固定的执行上限，不能把它解释成提供方美元账单或精确 token 计费。
- 完成 cell 前检查该任务全部 HTTP 和逻辑事件是否闭合；unknown 或未闭合请求拒绝完成。发生 source/data 变化，或遗留后台线程，持久记录 `run_invalid`；即使之后恢复原文件，也不能重新接受旧完成行。
- 候选源码逐 cell 校验，指定源码目录与数据库在结束时再整体核验。留存示例绑定 508 个 Python 文件，范围为 `ase`、`text_to_sql` 递归目录及两个新模块；包版本另列。不是任意外部导入依赖、系统库或提供方版本的完整冻结。

`fresh_collect` 使用真实 SQLHarness、SQLite 数据接口及新版本的只读 raw-set scorer。数值 1 与 1.0 相等、字符串 '1' 与数值 1 不等的规则保持；增加只读连接约束，避免预测 SQL 改写数据。这个执行器有自身源码身份，不能称为原 collector 未经修改的透明复现。

## 发现并关闭的实现问题

初版审核发现三类实质漏洞，均增加了行为检查：

1. harness 捕获超时后返回有效备用 SQL，可能把未知提供方状态标成完成。现在 HTTP unknown 会阻断 finish 和恢复。
2. 遗留线程可能在下一任务启动后借用新任务身份。现在 solver 不可换绑、关闭后的调用拒绝；采集器在 import 和 solve 返回时检查新增存活线程，有遗留则停在下一 cell 前。
3. 数据库最终校验失败后，把原文件恢复就可能重新接受已完成行。现在 invalid 状态持久保留，恢复原字节也不能放行。

其中第2项也用仓库原有 `cand_bird_g1_b0r1_g1` race harness 实测：本机提供方将同请求的一个响应延迟，harness 返回时另一线程仍活跃，采集器明确停止；再次执行也拒绝恢复。没有把该候选默认为错误答案或从种群里删掉。

## 验证证据

8 项新测试覆盖身份变化、第二写者拒绝、重复 fresh 请求、n=3、多线程、显式状态重试、usage 缺失、thinking 参数、捕获超时后的备用 SQL、延迟线程、永久 invalid、真实 bare/clone 跨进程恢复和只读评分。部分测试包含多个关联反例。完整 revision 套件66项通过；Ruff及论文原42项一致性检查通过。

留存示例为一个人工数据库、两个相同源码的 bare/clone 身份、两个 repeat，共4个 cell。实际发出4次回环 HTTP；独立进程再次运行新增0次请求。4份响应有人工编号，合计20个**人工设定**tokens，不能解释为模型多样性、真实消耗或科学结果。

证据文件：

- `artifacts/revision_20260910/fresh_runtime_smoke.json`：manifest、HTTP/逻辑事件、结果和跨进程恢复输出。
- `artifacts/revision_20260910/fresh_runtime_tests.txt`：完整 revision 套件结果。
- `artifacts/revision_20260910/fresh_runtime_verification.json`：当前源码、示例、测试与报告绑定。
- `artifacts/revision_20260910/requirements-runtime.lock.txt`：所用隔离环境依赖。

## 运行入口

在项目根目录使用已建立的 runtime 环境。以下入口本身不代表付费 API 执行已经获批：

```text
python -m experiment.revision.fresh_collect --config reviewed_acquisition.json
python -m unittest experiment.revision.test_fresh_runtime -v
```

配置必须显式提供 `acquisition_id`、`cache_mode: off`、`solver`、`api_key_env`、`dataset_root`、`split_path`、`protocol_path`、`repeats`、`harnesses` 和 `output`。正式固定资源实验还必须提供 `resource_budget`，包含正整数 `max_logical_calls`、`max_requested_samples`、`max_output_tokens` 和 `max_request_bytes`。每个 harness 项为 `id` 与项目相对 `source`；clone 可使用不同 id 引用同一份源码。示例构造和实际命令在集成测试中完整保留。持久权威记录是输出目录的 `ledger.sqlite`，成功导出的 `snapshot.json` 是其可读快照。

## 仍未完成，不能据此关闭的要求

1. **race / 遗留后台执行的完整支持。** 目前明确中止这类采集。下一步需要按任务进行进程隔离，并在进程终止后保留未决请求账本；不能通过静默剔除候选完成 A。当前 Thread 枚举也不是任意外部子进程的隔离边界。
2. **原运行政策的受控桥接。** 新版本改变重试、超时、客户端复用、执行顺序、环境覆盖和只读评分策略。当前按 repeat→harness→task 的固定顺序串行执行，不是随机化设计。必须在 C 中明确比较，不能把新旧差异归给科学处理。
3. **正式成本与执行独立性。** 尚无新真实提供方请求、实际 usage 完整性、金额或服务端缓存/路由证据。API 超时只说明客户端状态未知，不说明提供方计算已停止。真实小规模核验和预算仍待完成。
4. **科学协议及 A–D。** 稳定能力的有效推断、成本匹配、B 共同 raw pool 和独立校准、C 桥接、D 独立效用均未完成。协议文件的哈希绑定不等于科学协议已冻结或独立批准。

本轮两路审核各9/10 ready，仅针对上述限定开发实现；不是跨模型科学放行，也不是对全论文重新提分。
