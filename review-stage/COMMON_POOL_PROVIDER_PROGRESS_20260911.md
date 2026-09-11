# 真实共同候选池执行进度

2026-09-11。预算与模型已获用户授权；与原账本相符的12单元target接口先导已经完成（16次HTTP、8927已知tokens），详见PROVIDER_PILOT_RESULT_20260911.md。

## 原始双builder批次：停止、不完整

原设计GLM-5.3与Qwen3.8-Max按固定hash规则选出，两个generation seed、free/forced两条件、每条件每seed8槽、每槽3次，共192次。13项离线检查及跨模型启动审核通过，配置和源码11项绑定在启动前匹配。

实际只发出首个GLM请求，180秒ReadTimeout，未收到响应体和usage；完成0、未决1、未启动191。进程退出1，Qwen未启动，符合原异常停止规则。未知请求可能产生费用，不计为零，不自动重发。证据：artifacts/revision_20260911/common_pool_batch1/incomplete_audit.json及原始ledger.sqlite。

## 独立Qwen继续采集：运行中

因为Qwen尚未执行，在无任何生成质量或benchmark反馈时，另建common_pool_qwen_continuation，保留原Qwen全部96个request body和顺序，仅改变pool_id、输出、协议以及600秒读取时限。原双builder批次仍不完整；本次不重试未决GLM、不替换builder。全程仅保存响应、做文本提取和AST语法检查，未启动gate或benchmark。

新17项冻结绑定含原批次GLM账本与不完整审计。两个跨模型审核轴均9/10、ready（仅限定启动）；实际启动前17项再次通过，prepare与preflight相同。仍按固定96请求、零自动重试、异常立即停止执行；最大requested completion额度1572864 tokens不能作为实际usage或人民币金额。任何实际结论须等完整采集及独立对账。

## 论文与科学验收

目前没有新的A–D科学结果，论文实测表不改，整体仍4/10、not ready。软件/启动审核评分不能替代论文评分。下一步取得raw pool后，先冻结候选身份与源码，再按预先确定的政策作B同池对照；保持gate-v4首轮误放事实，未决profile不当作拒绝。A重复/clone和固定资源、C受控桥接、D独立效用仍需完成。


### 2026-09-10 Qwen continuation terminal audit

The separately frozen Qwen continuation stopped on a ReadTimeout at attempt 157 after 22/96 completed requests; 1 request remains unknown and 73 were not started. `pool.json` and `POOL_COMPLETE.json` are absent. All 17 freeze bindings match. The preserved audit is `artifacts/revision_20260911/common_pool_qwen_continuation/incomplete_audit.json`; no candidate-quality analysis or automatic resend is authorized by the frozen protocol.

### 2026-09-11 continuation attempts after the 22/96 stop

Two separately identified continuation directories were observed to terminate and were audited from their SQLite ledgers. `common_pool_qwen_continuation_72_v2` registered 14 of 72 planned attempts: 13 returned results and 1 remained pending after an `http_start` with no matching completion event. `common_pool_qwen_continuation_73` registered 1 of 73 planned attempts: it remained pending after an `http_unknown` event and 72 attempts were not started. Neither directory contains `pool.json` or `POOL_COMPLETE.json`.

The terminal audits are `artifacts/revision_20260911/common_pool_qwen_continuation_72_v2/incomplete_audit.json` and `artifacts/revision_20260911/common_pool_qwen_continuation_73/incomplete_audit.json`. The partial returned responses are retained for provenance only. They are not merged, gate-scored, benchmark-scored, or used for quality, cost, superiority, or A--D claims; pending and unknown provider requests are not retried automatically.

### Offline R3 same-code diagnostic

The existing three cache-off repeats of the same `bare` source on the 400-item core were replayed without model calls. If the three executions are incorrectly treated as three population members, the descriptive one-run oracle is 72.25%, best fixed is 65.75%, and the apparent gap is 6.50 pp; pairwise repeat disagreement is 9.25--10.00%. The result is recorded in `artifacts/revision_20260911/r3_bare_repeat_diagnostic.json`. Because all three source hashes are identical, this is a same-code resampling diagnostic only: it does not estimate `H_stable`, real-vs-clone advantage, selector utility, or any A--D result.
