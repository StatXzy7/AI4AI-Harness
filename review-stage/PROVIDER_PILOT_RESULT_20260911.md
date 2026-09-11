# 授权后的真实提供方接口先导：已完成

2026-09-11。用户已明确授权继续使用 paratera-glm-ziqian 及论文内模型，预算几千人民币。实际核对该连接与历史实验密钥相同；保守按2000元作为内部研究规划上限，不声称这是用户指定的精确金额或程序硬额度。此前“没有预算授权”已不再是阻碍，不能继续沿用历史待授权状态。

本次仅为固定12单元接口先导：两个已曝光开发题×bare/同源bare_clone/race×两个repeat，目标GLM-5.3-Flash。原定任务、顺序、timeout、max_tokens及零重试保持。不同模型的协议与机械启动审核各8.5/10 ready，限定本次先导；8项Windows隔离测试通过。配置、协议、preflight及连接记录冻结后，在真实启动前逐项复核，prepare结果与冻结manifest完全相同。

## 实际账本

- 单次运行约47.4秒，进程退出码0；12/12 completed，0 pending，0 not-started。
- 16个HTTP starts与16个HTTP ends逐一对应，全部200；16个逻辑调用已结清，无自动重试。
- prompt tokens 8088，completion tokens 839，总8927。提供方报告的539 reasoning tokens包含在completion内，不另加总。
- 提供方报告cached prompt tokens 448。应用层cache-off仍保持；该字段不证明答案缓存或采样不独立。
- 16个response ID存在且互不相同；request-header ID未返回，保留缺失，不伪造。
- 四个race单元在返回答案后仍有HTTP响应；迟到响应均已进入最终账本，没有因答案提前返回而漏计。
- 12个worker退出码0，Job清理后active_processes均为0。
- 完成后复核510份源文件及1个数据库文件哈希（两道题均来自card_games）。父账本总tokens与逐请求汇总一致。

`thinking_style=none`在此客户端表示不发送特定thinking切换字段；它不等同于模型没有推理，实际response usage中的539 reasoning tokens必须保留。输出token总数839已包含它们。

## 结论与下一步

已取得真实API返回、完整token账本、并发迟到响应归属及进程收尾证据，不再只依赖本机mock。运行完整性通过；缺失request-header ID、账户单价和实际人民币对账仍明确保留。20元只是先前先导额度建议，没有验证为实际成本或硬限。不能从16个不同response ID推导提供方独立性，也不能从两道曝光题的答案推导真实种群、clone或策略的科学优劣。

本次没有扩展到A-D正式实验或修改论文实测表。下一步结合这些实际返回字段冻结A的重复/时间交错/资源预算与失败规则，并准备同一raw pool上的B/C对照。正式规模需按实际费用规划；不再要求用户重复批准已授权的连接和模型。独立效用D与W1总体推断仍未完成。

证据目录：`artifacts/revision_20260911/authorized_provider_pilot/`；冻结配置、启动复核、原始SQLite账本、每个worker日志、snapshot及completion_audit均保留。凭据未写入新产物。
