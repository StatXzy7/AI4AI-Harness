# 任务进程隔离：保留 race 答案与未决请求

日期：2026-09-10。新增 `isolated_collect.py`、`windows_job.py`；上一阶段 fresh 版本、历史 collector 及论文产物保留。

**限定开发实现 ready；正式 A–D 尚未放行。** 当前支持真实 race harness 的每任务进程执行，不再因正常的较慢竞争请求而直接拒绝候选。仍不把提供方未知状态、缺失成本或部分完成数据视作实验完成。

## 本轮改变

每个 cell 使用独立 worker 和独立 SQLite 请求账本。父进程在整个采集目录持有写锁，按声明的 repeat→harness→task 顺序调度。完整 manifest 仍绑定任务、种群身份、源码、数据库、协议、请求设置和包版本，并增加 worker wall 与 drain 时限。

Windows worker 以挂起状态创建，加入 Job Object 后才恢复执行并打开启动闸门。这样连虚拟环境启动器派生的解释器也在受控树中。Job 配置 kill-on-close，不允许主动 breakaway；父流程正常/异常退出均保留清理路径。测试覆盖普通子进程树的显式终止，完成判据是查询到活动进程数为0。该机制依据 [Microsoft Job Objects 文档](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)；它不是恶意代码安全沙箱。

`solve()` 返回时立即保存不可变的 SQL 与 `answer_seconds`。随后在同一任务身份下等待已启动的后台线程，最多等待配置的 `drain_seconds`。较晚的回复会进入当前任务账本，但不会替换已返回答案。答案时间只测 solve；worker wall 还覆盖进程启动、等待与清理，不能混作同一个延迟指标。

若后台线程在期限内完成，所有逻辑/HTTP记录闭合、无 unknown、评分与源码检查通过，则 worker 写入候选完成结果。父进程仍须确认 Job 已清空，才导入子账本并接受该 cell。子账本事件 ID 在父账本重新映射，logical/sample/attempt 关联保持；原 worker event ID 和原时间戳同时保留。

若 drain 到期或 worker 超过 wall 时限，父流程清空本地进程树、读取已提交账本、保留已返回 SQL 和未配对的请求起点，当前 cell 保持 pending，并停止整个采集。不会自动重采，也不会推进下一 cell。

## 崩溃账本与修复证据

审核发现仅用 SQLite 只读模式打开被强制终止的 worker 账本，会因未回滚的 hot journal 失败。现在只有在 Job 已确认活动进程数为0后，才用 `mode=rw` 打开已有数据库以完成 SQLite 恢复；不会创建缺失账本。若数据库仍无法读取，则记录 `ledger_read_error` / unknown、保留原文件和 pending 快照，继续禁止自动重试。

另修正了两处 Windows 细节：标准输出和错误输出共用句柄时，继承句柄列表必须去重；进程根句柄结束后 Job 计数可稍有滞后，因此先短暂等待清空，再决定是否终止存活后代。`limit_terminated_processes` 只指因限制违规终止的计数，不能用它衡量主动 kill 的数量；依据是 [Microsoft accounting 定义](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information)。

5 项新增测试分别覆盖：

1. 挂起 worker 在归入 Job 前不能派生后代；启动后整个正常子进程树可终止并确认活动数归零。
2. 原有 `cand_bird_g1_b0r1_g1` race harness 的两个 repeat 使用不同 worker，慢回复在答案返回后仍归同一任务；跨进程恢复不新增请求。
3. 短 drain 保留已返回答案、1个已完成与1个未完成请求；pending 恢复被拒绝，不自动补采。
4. worker wall 超时终止本地 Job，仍保留提供方请求未知状态。
5. 在实际 SQLite 写事务中用 `os._exit` 中断，随后恢复200条已提交事件和 pending 状态，不把未提交写入当证据。

## 留存的回环结果

以下均为人工数据库和本机 HTTP 服务，实际执行 SDK 与原 race/bare 代码；不是模型实验。

| 场景 | 已发 HTTP | 完成 cell | 留存状态 |
|---|---:|---:|---|
| race，2 repeats，允许3秒 drain | 4 | 2 | 不同 worker；每 cell 2请求、10个人工 tokens；恢复新增0请求 |
| race，0.05秒 drain | 2 | 0 | 答案已返回；1请求完成、1请求未决；不推进第2个 repeat |
| bare，4秒 worker wall、服务端延迟 | 1 | 0 | 无已完成响应；本地 Job 已清空，提供方状态仍未知 |

三组留存结果均确认父流程结束当前 worker 时 Job 活动进程数为0。示例绑定510份指定目录源码。源码绑定不等于每份文件都执行过，也不冻结任意外部导入依赖或提供方实现。

证据：`artifacts/revision_20260910/isolation_smoke.json`、`isolation_tests.txt`、`isolation_verification.json`。完整revision套件71项通过，Ruff和论文原42项一致性检查通过。独立机械审核与 Spec 审核各9/10 ready，仅针对限定开发实现；不构成跨模型科学放行。

## 使用及下一步

在 runtime 环境中运行：

```text
python -m experiment.revision.isolated_collect --config reviewed_acquisition.json
python -m unittest experiment.revision.test_isolated_collect -v
```

配置沿用 `FRESH_ACQUISITION.md` 的字段，另需显式提供正数 `drain_seconds` 和更大的 `worker_wall_seconds`。输出根目录 `ledger.sqlite` 是父账本，`workers/<cell-key>/` 保留请求配置、子账本与 stdout/stderr；`snapshot.json` 是可读快照。协议文件存在并有哈希，不等于协议已完成科学冻结。

正式推断前仍有四项直接相关的余项：

- pending 不能静默删掉、按错误填零或重采后挑选结果。只分析 completed cells 会按延迟和成本选择样本；必须先冻结失败/未决处理规则，再形成完整分析集。
- Job 活动数为0只证明本地树结束，不证明提供方停止计算、取消计费或统计独立。账本也只覆盖配置的冻结 solver 通道，不能保证任意 harness 自建客户端的请求都被计量。
- drain、进程重启、串行顺序、重试/超时和只读评分是新执行政策，须在 C 的受控桥接中明示，并纳入成本匹配。人工 tokens 无实际金额含义。
- 尚未执行新的真实提供方小规模核验，也未完成预算、A 的稳定能力推断、B 共同 raw pool / 独立校准、C 桥接或 D 独立效用。整体仍 not ready。
