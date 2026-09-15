# WP-1R G1 预算门冻结（v1.3 修订，2026-09-15/16）

状态：**FROZEN**（对应 REAL_EVIDENCE_PROTOCOL_V1.md 的 v1.3 追加；
G0 于 2026-09-15 第四轮以 8.8/10 ready 通过；本文档闭合 G1 的预算条件。）

## 1. 已完成的 G1 实测

- **Provider 冒烟**（`experiment/revision/provider_check.py`，2026-09-16）：
  - key 源：`experiment/.env_tthe`（历史采集同一凭据；不打印、不入库）。
  - `GET /models`：HTTP 200，93 个模型，**GLM-5.3-Flash 在列**。
  - 3 次最小 chat 请求全部 HTTP 200：temperature=0.0 接受；seed 参数接受
    （不报错）；max_tokens=1 接受；返回 model=`GLM-5.3-Flash`；
    usage 完整（prompt/completion/reasoning/cached tokens）。
  - 供应商不返回 x-request-id 请求头（响应 `id` 字段可用，已逐请求入账）。
  - 全部请求写入 `artifacts/wp1r_20260915/provider_audit/provider_ledger.jsonl`
    （完整请求/响应体，无认证头）。
- **正式 pilot**（`fresh_collect_math --config configs/pilot.json`）：
  3 dev 任务 × bare × repeat 1，3/3 cells SUCCEEDED（official_correct=1），
  每请求 usage 完整，全局账本 reserved=3/45000。
  RunStore sqlite 即 pilot 的持久请求账本（A8.8）。

## 2. 定价核验状态（如实）

- 虚拟 key 被网关限制为 llm 路由（/models/<model> 403 明示），无余额/价格端点；
- 公开网页 403（与 `PROVIDER_ACCOUNT_READINESS.md` 的历史结论一致）；
- 历史 12 单元先导（2026-09-11）同样"账户单价与人民币对账明确保留"。
- **结论：单价不可核验。** 按协议 A2，不虚构金额；预算门改用**保守上界
  断点价**闭合（§3）。

## 3. 预算门（token 账本 × 断点价）

冻结假设（保守方向）：
- p95 每 attempt tokens = 2004（pilot bare 均值 802 × 2.5，覆盖成员
  scaffolding 提示与多采样；实际多数调用预计远低于此）；
- attempt 预算 = 45,000（含重试与 5 采样调用），全部按 p95 计价；
- 投影总 tokens ≤ 45,000 × 2,004 ≈ **90.2M tokens**；
- **断点价 = 4000 / 90.2 ≈ 44.3 CNY / 1M tokens**：单价低于此值时，
  即使全部 45,000 次请求都达到 p95 token 量，总成本也不超过 4000 CNY。

执行规则（冻结）：
1. 采集全程以 token 账本累计（`known_total_tokens`）；账本同时给出
   "按断点价 44.3 CNY/1M 折算的保守成本上界"，随 CHECKPOINT 报告；
2. 若供应商账单/后续核验得到真实单价，以真实单价重算并如实报告差额；
3. 若保守上界逼近 4000 CNY（>3,600），暂停采集并报告作者；
4. GLM-5.3-Flash 为 flash 档模型，其市场公开报价历史上远低于断点价
   （历史先导 16 请求 8,927 tokens 亦无超额迹象）；此为背景说明，
   不作为定价证据。

## 4. attempt 预算核对

- eval_real：9 成员 × 400 任务 × 3 轮 ≈ 21,795 logical calls；
- eval_clone：9 槽位 × 400 × 3 = 10,800；
- dev_real：≈ 5,449；pilot 已用 3；冒烟 6；
- 合计 ≈ 38,053，含重试余量后硬上限 45,000（共享账本强制）。
- 5 采样成员（kimi_g3/minimax_g3）按 samples 计 attempt（每 sample 一次
  HTTP），已含在 per-cell 样本感知预算内。

## 5. G1 判定

- 冒烟：PASS（模型/参数/usage/账本全通过）。
- pilot：PASS（正式采集器端到端、3/3 成功、账本完整）。
- 预算门：PASS（保守上界闭合于 4000 CNY 之内；断点价 44.3 CNY/1M）。
- **允许启动正式采集**（eval_real → eval_clone → dev_real 顺序，
  共享全局账本，并发 2 起步，验证稳定后升至 4）。
