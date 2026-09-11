# 提供方用量口径：请求上限不是已验证的实际上限

2026-09-11。对运行中Qwen池的前5份已返回响应，仅核对HTTP请求参数、原始响应body hash和usage字段，没有读取候选质量或计算中间效果。5份原始body均与账本hash一致，JSON中的usage与http_end记录逐项一致。

其中一份请求max_tokens=16384，但提供方报告prompt_tokens=287、completion_tokens=18889、total_tokens=19176。账本没有重复叠加reasoning字段；这是原始响应本身的计数。原因未明，不能据此断言参数被完全忽略，也不能把其内部text/reasoning字段自行相加重算账单。后续以顶层prompt/completion/total记录实际提供方usage，保留全部细分字段待对账。

原协议“96×16384”的额度只能表示请求参数总量，不是实际输出或人民币硬上限。当前保持96个预定请求、零自动扩容；与已停止GLM请求的未知状态/费用分开保存。当前已知token汇总不等于整个研究的完整费用。

只读账户兼容性探测GET /v1/dashboard/billing/subscription及GET /v1/usage均返回404，无单价、余额或费用字段；它们不是已获文档确认支持的接口，也不是生成请求。没有保存密钥或完整账户响应。官方MaaS介绍列有自助计费、按API Key统计等功能，但不提供本账户这些模型的实际报价，因此不能替代账户对账：https://www.paratera.com/mass.html 。

这份检查不撤回用户对连接、论文模型及几千元预算的授权，也不据此重发未知请求或新增实验规模。下一阶段费用规划必须使用账户适用单价及实际usage，不能靠max_tokens作未验证的硬费用保证。完整候选池、A–D科学实验及提分仍未完成。证据：artifacts/revision_20260911/account_readonly_check/result.json、raw_usage_check.json。
