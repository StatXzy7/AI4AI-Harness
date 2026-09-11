# B/C共同原始候选池：首次真实批次

用户已授权paratera-glm-ziqian及论文模型，预算几千人民币；沿用2000元保守内部规划上限。本批是已授权研究的共同候选池生成，不是追加授权请求。单批192个请求，无自动扩容；实际tokens完整记录，人民币成本待账户对账，不声称程序执行人民币硬额度。

固定既有六builder列表，按SHA256("revision-common-pool-v1|"+builder)升序取前二：glm(GLM-5.3)、qwen(Qwen3.8-Max)。次序记录，不依据生成质量选择。两个新generation seed为20260911和20260912。每seed含8个free槽和按旧STRATEGIES原序排列的8个forced槽；每槽完整生成3个候选，共2×2×2×8×3=192。每builder的32槽按SHA256("slot-order-v1|"+slot_id)顺序执行，不能看到回复后改顺序。

PROMPT_FREE、PROMPT_FORCED、DECLARE、SKELETON和STRATEGIES从旧generate.py用AST提取常量，原文保持，仅代入类名、策略、skeleton。相同seed/槽序号的free与forced共享同一类名，差别来自固定提示条件。每次采样的requested seed为generation_seed×100+slot_index×3+attempt_index，free/forced对应尝试使用相同seed；不据此声称提供方独立或seed有效。temperature0.7、n1、max_tokens16384、timeout180秒，无状态重试、无重定向、无应用缓存，保留provider cache/usage字段。

builder顺序glm再qwen。任何传输/响应结构/usage异常停止当前池且不启动后续builder；已经返回的响应字节、已完成与未决attempt均保留，不自动补采。语法/围栏提取错误不重生成、不减少分母；即使第一次成功也继续三次。所有原始body在解析前写入SQLite，源码只做AST语法检查，不导入、不执行、不修复。

完成后先冻结raw pool，再离线实施neutral、历史screening-v1及新gate政策。新版gate-v4仍有首测误放的已知限制，其原参考首测结果不得被覆盖。本批不因gate结果改变生成，不使用benchmark反馈。对未能适配新版合同的源码预分配profile或未决标签，不能默认为拒绝。B准入比较、固定K和C旧新桥接的具体评估清单须另行冻结；POOL_COMPLETE只说明固定生成与token账本完成，不表示候选合格或科学验收完成。

同一raw pool有利于控制生成差异，但不能单凭此批生成就宣称解释了历史阶段间效果变化。A仍需重复/clone/时间交错/资源匹配，D仍需独立数据和冻结选择器。此批生成只为这些必要后续实验提供完整、不受筛选反馈影响的候选来源。

计划最大requested completion额度为192×16384=3145728 tokens，不是实际usage或人民币报价。当前接口先导已证明连接和target用量字段可用，builder结构仍由实际返回验证。所有代价按两个builder分别汇总，不能用target SQL请求均值直接预测代码生成费用。
