# 提供方先导 v2：启动与缺失 usage 停止规则

2026-09-10。状态：本机验证完成；真实先导 not ready to launch。本文是阶段12 `PROVIDER_PILOT.md` 的执行修订，不改变两道已曝光开发题、bare/clone/race、两个 repeat 共12 cell 的仪器范围。原协议中“DRAFT 不是程序闸门”和“usage 缺失仍继续”的描述仅适用于 v1；v2 以下述规则取代。其余参数、失败分母与科学边界沿用原协议。

## 两项实际修复

1. `isolated_collect.collect` 在 prepare、读取数据或创建输出之前拒绝含 DRAFT（大小写不敏感）或空白的 acquisition identity；直接 worker 入口同样拒绝。prepare 本身仍接受 draft，供断网审阅。去掉 DRAFT 字样不表示已获预算或科研批准；这是防误启动检查，不是权限系统。历史 `fresh_collect` 不作为本先导入口。
2. 每个 worker 的请求结清且本地 Job 清空后，若任一响应 usage 缺失或无法按现有规则解析，父采集器保留已返回 SQL、评分、子账本和未知成本信息，发出 `response_usage_unknown` 停止事件。父 cell 保持 pending，不启动下一 cell，不自动续跑。子账本的 completed 仅说明答案与请求状态已结清，不能冒充父采集验收完成。

新 manifest 版本为 `isolated-acquisition-v2-development`，绑定 `missing_usage_policy=stop-before-next-cell-preserve-pending-v1`。旧运行 manifest 不匹配时拒绝恢复。不会将缺失 usage 的答案计错、删除，或另采一条代替。

停止发生在当前 cell 的请求完成之后；race 内已经发出的并发请求或 repair 仍可能收费。usage 字段完整也不能证明服务端内部重发已全部计账。因此本检查不是请求前费用预留，也不是人民币硬上限。金额授权、账户价格与保守费用界或提供方硬额度、最终非 DRAFT 冻结仍需完成，当前不得付费启动。

## 本机证据与版本边界

Windows runtime 环境运行完整 revision suite：81 项通过，含8项隔离测试（原5项，加DRAFT CLI、直接worker、缺失usage停止/续跑三个用例）。缺失usage的回环提供方返回正确SQL，父账本保留答案但pending；第二cell未启动，再次运行不新增HTTP。已有race迟到响应、drain过期、wall超时、进程树和SQLite恢复用例继续通过。所有提供方响应均为本机合成数据；新增真实生成请求为0。

阶段16证据入口为 `artifacts/revision_20260910/launch_guards/verification.json`，配套 `preflight.json` 为新v2草案的断网prepare结果。测试日志留在同目录。`before/` 保留修改前的隔离采集源码和测试；旧阶段11/12证据不改写，旧source绑定通过保存的v1源码核验，不称其为对当前v2的验收。阶段12原协议、draft和preflight仍保留历史身份。

最初不同模型审核（执行GPT-6，审核gpt-5.5）给先导包7/10、not ready，指出上述两个启动缺口；修后复核记录单独存于本阶段verification，以免把软件作用域通过混同于启动许可或论文提分。

论文的实验数字、英文/中文源码及PDF本阶段均未改。A独立重复与成本匹配、B独立校准及共同候选池、C受控桥接、D冻结后效用、W1正式推断仍未关闭。整体论文沿用原审稿4/10、not ready。
