# 完整采集链路的离线恢复检查

日期：2026-09-10。状态：**本机合成链路已跑通，正式重复执行与成本采集仍 not ready**。

这是审稿意见中复现、重复独立性和计算成本要求的准备工作。没有新 BIRD 实验结果，没有付费模型请求，也不据此给论文提分。历史源码、缓存、结果和两版 PDF 均未改动。

## 本轮实际执行了什么

在新的 CPython 3.13.9 隔离环境中安装 OpenAI SDK 2.24.0、PyYAML 6.0.3 及锁定依赖。使用 `provider=openai`，请求发送至本机 `127.0.0.1` 的临时 HTTP 服务。服务端返回人工编写的 completion、响应 ID 和 usage；不是 `provider=mock`，也没有用替身 bridge 或 AST 抽取函数。

实际调用链为：原 `collect.main` → 原 `load_harness` / `BareHarness` → 原 `SQLHarness.llm` → 原 bridge / `SolverCache` / `LLM` → 真实 SDK 与 HTTP → 临时 BIRD 格式数据 → 原 SQLite 执行器和项目 `official_scorer`。项目 scorer 是仓库中的 BIRD 规则实现，不能称为另外运行了外部官方评测程序。四个评分控制覆盖数值类型、字符串类型、重复行、执行错误。

为隔离数据，配置、输出、split、BIRD 根目录均重定向至系统临时目录；没有读取真实 BIRD 题目或 gold。各次 collector 在同一新子进程中串行调用，不能据此声称验证了跨进程并发、崩溃恢复或线上提供方独立性。`n=3`、重试和 thinking 检查从真实 harness 接口直接调用；collector 的对应逻辑计数由源码及单样本行确认。

记录保留每轮 stdout、四条采集行、服务端请求/响应账本和选定的 11 个测量路径源码 SHA256；执行前后源码必须一致。账本不记录认证头。重试用例对 SDK `create` 加了透传计数包装，仅计数，仍调用其原实现。临时服务、数据库、缓存于结束后清理。

## 已证实的行为与阻断项

| 检查 | 当前观察 | 对正式实验的含义 |
|---|---|---|
| 首次采集 repeat=0 | 1 次 HTTP，写入 1 行 | 合成完整链路可运行 |
| 同文件同 repeat 恢复 | 0 次 HTTP，没有新增行 | 恢复路径生效 |
| 开缓存改为 repeat=1 | 0 次 HTTP，新行复用 reply 1 | repeat 标签不保证 fresh 请求 |
| repeat=2、3，`--no-cache` | 每轮 1 次 HTTP，分别 reply 2、3 | 此受控路径确实旁路缓存；不证明线上随机独立 |
| 同文件同 repeat=0 切到 `--no-cache` | 0 次 HTTP，保留原 cached 行 | 恢复键遗漏缓存条件；条件改变会被静默跳过 |
| 同请求、两实例的 seq=0/1 | HTTP 增量为 1/1/0/1；seq0 相同，seq1 不同 | 尚未 flush 的值没有进入可命中的内存数据；缓存不保证同 key 同回复 |
| 一次 `llm(n=3)` | 1 条逻辑 trace，3 次 HTTP，3 个响应 | `n_llm_calls` 不是模型样本数或物理请求数 |
| 429 后成功 | 1 条 trace、1 次 SDK `create`、2 次 HTTP | SDK 内部重试没有体现在逻辑计数中 |
| 服务端成功响应带 usage | 响应均带人工设定的 18 tokens；采集行没有 usage / response ID | 当前返回链路只保留文本，无法恢复真实账单 |
| thinking_style=deepseek，请求温度 0.7 | HTTP 有 thinking/reasoning_effort，没有 temperature | Python 参数和缓存键中的温度不等于实际发送的温度 |

未刷盘反例把 flush 间隔设为足够长，从而稳定观察默认 30 秒间隔中也存在的窗口；没有改变 `SolverCache` 的逻辑。这是缓存一致性缺陷的确定性反例，不是历史实验受影响频率或效应大小的估计。回复只因人工附加的 ID 注释而不同，不能将这种差异报告为 SQL 语义或准确率变化。

恢复键在源码中还遗漏 `code_hash`：同 harness 名下源码变化也不会使已有行失效。本轮未实际更改 harness 源码，因此这一点是源码确认，区别于已动态验证的 cache-mode 切换。

项目两种 judge 的合成结果分别为：`SELECT 1` 对 `SELECT 1.0` 为 official=1/legacy=0；字符串 `'1'` 对整数 1 为 0/1；重复相同行为 1/1；错误列为 0/0。它们验证实际实现差别，没有新增任务层结果。

## 下一步必须交付的运行修改

1. **A 的 fresh 路径在启动时明确旁路缓存，并保存实际执行身份。** 每条记录关联 acquisition/repeat、任务、完整源码哈希、提供方和实际请求配置；不能只改 repeat 标签。线上提供方的缓存、路由或模型漂移仍需真实响应证据。
2. **恢复执行必须校验整个运行条件。** 对同输出文件的缓存模式、源码、任务清单、模型参数或 judge 变化报错；不能把旧行当新条件的完成证据。这个检查不得悄悄重写历史输出。
3. **补充请求与成本账本。** 分别保存逻辑调用、sample、物理 HTTP attempt、重试、缓存命中、响应 ID、usage、缺失 usage 和未决请求；unknown 保持 unknown。金额另需提供方价格或账单，人工 fixture tokens 不用于预算。
4. **冻结实际发送的参数。** 保存 thinking 分支和发送内容，不把未发送的 temperature 描述为已控制变量。超时后仍在后台运行的请求也须可见，避免把未决采样算成已结束。
5. 对上述修改完成成功、失败、重试、条件不匹配和恢复用例后，再做经授权的真实提供方小规模成本/独立执行检查；随后冻结 A–D 正式协议。当前探针的通过不能替代这些工作。

本轮不直接修补被历史产物哈希绑定的上游代码。后续新增运行版本应保留旧版本和差异，让 C 的受控桥接能够明确区分实现修复与科学处理。

## 可复跑入口与证据范围

在 Windows 项目根目录，使用 `artifacts/revision_20260910/runtime_env/Scripts/python.exe`：

```text
python -m experiment.revision.runtime_probe
python -m unittest experiment.revision.test_runtime_probe -v
```

完整环境依赖见 `artifacts/revision_20260910/requirements-runtime.lock.txt`。新六项测试主动断言当前的若干缺陷确实存在；测试 PASS 表示诊断可复现，**不表示缺陷已修复**。原 52 项测试与新六项分开标注，并在同一 runtime 环境中执行完整套件。结果和最终核验见 `runtime_probe.json`、`runtime_probe_verification.json`。

正式 A 的稳定能力识别、B 的共同 raw pool / 独立校准、C 的受控桥接、D 的独立效用，以及真实成本匹配仍未完成。当前论文整体沿用未重评的 4/10、not ready。
