# 同一回复的旧新提取配对检查：入口已验证

新增experiment/revision/common_pool_extraction_compare.py。它在外部hash冻结且经过单独完整性审计的pool.json上，对每份相同message分别运行原extract_block与新extract_python，保留所有attempt及其条件、策略、seed身份。输出语法有效性四格表和代码hash，不运行候选，也不计算neutral、准入或benchmark效果。

三项离线测试、Ruff通过，格式修正后测试再次通过。独立机械审核8/10 ready with warning（格式已修正）；spec首评对marker路径要求的误解经澄清后撤回，最终9/10 ready。固定伴随POOL_COMPLETE.json是生产者输出，不需要另加可任意指定的marker路径；外部pool SHA才是本入口的预期字节约束。该检查仍不替代逐HTTP、body、usage完整性审计。

8项源码/协议/人工输入绑定后，命令行在已归档六请求人工loopback上退出0，保留6行和完整分母。结果不是新提供方候选的统计，不能据此证明修订后生成更好。真实Qwen96池仍在运行，完成并审计前不得将部分数据送入该最终分析。

运行形式：python -m experiment.revision.common_pool_extraction_compare --pool COMPLETE_POOL/pool.json --expected-sha256 EXTERNALLY_FROZEN_POOL_SHA --output NEW_RESULT.json。输出路径必须不存在；真实使用时先核对本入口freeze.json的实现绑定，再使用采集审计冻结的池SHA。

本工具只为受控桥接中的提取环节提供可执行比较。C仍需固定生成/目标/题集/judge/cache/时间块，A重复/clone、B完整处理定义与独立校准、D独立效用仍未完成。论文整体4/10 not ready，当前没有新实测表或PDF修改。证据在artifacts/revision_20260911/paired_extraction_preflight/。
