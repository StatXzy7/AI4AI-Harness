# 新共同raw pool生成入口：实现合同

阶段23，2026-09-10。此文件是开发实现合同，不是实际实验冻结或费用批准。旧生成器及历史候选不修改；不重建丢失的历史回复。

生成条件只有free/forced；neutral、screening-v1及新版gate在同一完成后的pool上离线应用。每个槽位预先给出三次seed和相同messages、模型、温度及token上限。首次有效代码不提前停止；语法错误不补采。网络状态、回复结构或usage不完整时保留已发生请求并停止，整个pool仍不完整，不以少于三次的槽位冒充固定三次完成。

HTTP响应体在content-encoding解码前通过iter_raw读取，并先在SQLite账本中提交原字节及content-encoding/content-type，再单独解码、解析JSON及代码；不声称保存TLS、HTTP传输分帧或全部headers；解码后的content、提取状态、代码、语法错误、finish_reason、报告模型、请求参数和usage均保存。响应源码不导入、不执行、不进行准入；语法有效不等于neutral有效。没有应用层缓存、状态重试或重定向，环境代理关闭；这不证明提供方不存在缓存或重复执行独立。

提取合同：接受完整raw文本或单个Python围栏。Python字符串内部的独立围栏行通过词法状态识别，内嵌SQL围栏保留；不按“哪段代码能编译”选择较好代码块，不拼接多个Python块，不补全代码或缺失围栏。多个Python块和无法识别关闭边界的回复保留为提取失败。后续准入政策须看到这些记录，不能静默删掉它们。

运行身份绑定完整配置、固定槽位/seed/messages、协议文件和实现源码。使用既有RunStore的单写者锁、逐事件提交、未决任务拒绝自动恢复及持久invalid机制；完成后可导出同一pool而不重新请求。POOL_COMPLETE仅表示固定计划全部完成且token计数完整，金额仍未知，也不表示科学或生产放行。

配置包含status（DRAFT/FROZEN）、pool_id、builder（base_url/model/max_tokens/temperature/timeout_seconds）、protocol_path、output、api_key_env和slots；每slot包含id、generation_condition、strategy、seeds（三整数）和固定messages。`--prepare-only`不需要密钥或网络。实际执行必须使用已审核的FROZEN计划并取得对应费用授权；本阶段仅允许模拟transport及本机回环HTTP验证。

验收要求：保留stage22的三个合法内嵌围栏反例，补充多行字符串/CRLF/多Python块/缺失围栏；验证三次完整请求、坏代码不补采、原响应先于提取提交、无重复恢复、usage未知及超时停机、输入恢复不能洗掉invalid。需两轴代码审核和独立模型复核。共同pool的真实生成、完整gate及A–D/W1科学验收仍待完成。

## 本阶段验收结果

13项专项测试、Ruff通过。新增gzip原响应体逐字节核对、缺消息结构停机及未决恢复拒绝、完成标记导出中断后零请求恢复。缺content字段与content=null分开：前者结构错误停池，后者保留missing_text，不虚构代码。三seed由配置固定，未强制互异，不据此声称提供方采样独立。

保留演练位于`artifacts/revision_20260910/common_pool_generation/loopback/`。真实传输仅发生在127.0.0.1：free/forced各3次，共6请求；人工构造2份语法错误仍留存，gzip压缩body与服务器源字节一致，再次collect新增0请求、pool.json字节不变。两个条件使用同一人工提示，只测调度，不测free/forced策略效果。token全为人工值，不支持成本或模型行为结论。

机械初审6/10 not ready指出自动解压和缺message误完成，修后9/10 ready；gpt-5.6-sol独立合同初审8.4/10 almost，修后9.5/10 ready（执行者GPT-6）。两位复核时独立跑过12项测试；随后只加强未决断言并新增导出中断测试，最终13项由执行者通过。审核未验收真实provider或科学实验。代码/合同与演练来源哈希见本阶段verification.json。

本阶段不改旧生成器、冻结gate或论文统计结果；论文/PDF沿用阶段22。下一步为八类接口/响应角色、共同pool真实计划及费用界、完整独立校准。A重复/clone/资源匹配、C受控桥接、D独立效用和W1正式推断仍未完成，论文整体verdict仍为not ready；不把软件9.5分换算为论文评分。
