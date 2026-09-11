# Gate-v2 独立构造控制：测量前固定规则

2026-09-10。范围：当前开发探针及四类语义审阅流程的首批独立构造控制，不运行benchmark、raw候选生成或付费模型API，不关闭B实验。先固定仪器，再构造并冻结控制源码，最后测量；本轮不修改仪器或按结果修控制。

## 来源与最小样本

控制作者使用新上下文gpt-5.5，区别于仪器实现者GPT-6；仅接收原合同第1至3节及公开调用接口。不得读取gate_v2.py、gate_controls.py、旧开发/语义packet或结果。每类repair、vote3、schema_link、hint_guard、two_view、decompose、error_classify、format_guard各两正两负，共32例。正例应以不同程序组织实现声明；负例应是相关的错误实现。禁止按已知probe名称、salt、marker、期望SQL或控制标签分支。

作者给出源码、固定作者参考标签及理由；作者标签是人工构造机制的参考定义，不是假定无误的自然种群真值。没有从生成种群随机抽样，样本比例人为平衡；仅报告本控制集分类型计数和条件比例，不外推总体误放/误拒率或以小样本完美命中证明校准可靠。

公开接口：每个可调用对象`solve(io, question)->非空SQL字符串`，`io.schema`为字符串，`io.llm(prompt, system='', temperature=0., n=1)`返回字符串（n>1时字符串列表），`io.execute(sql)`返回`{ok:bool, rows:list, error:str|null}`。控制不得调用外部服务、文件、进程或网络；仅标准库纯计算。decompose的计划响应遵循公开合同的JSON字符串列表格式。标记携带原样信息不代表一般语义正确。

## 固定执行与裁决

控制落盘后先做语法与接口检查、SHA256冻结；检查阶段不执行gate或根据gate结果编辑控制。若存在代码无法运行的缺陷，首次完整测量仍记录execution_failure，解释它是fixture兼容性问题或实现问题；修订控制另立版本，不擦去首次结果。

父执行者运行冻结的`evaluate`一次遍历32例；采用固定salt `independent-v1-20260910`，原始完整trace留存。该salt只改变已有合成标记，不构成新的probe覆盖。测量后源码不变，原始结果不可替换。

四类语义机制hint_guard、format_guard、two_view、error_classify的所有16例（包括结构fail）交给不同于控制作者和测量执行者的审核模型gpt-5.6-sol，提供源码和完整trace，不提供作者标签或自动判决。每例conforms/nonconforms/indeterminate及证据字段。对其余四类repair、vote3、schema_link、decompose，审核者做源码合同复核并记录作者参考定义是否存在争议；不以评测结果校正原标签。最多一轮纯证据/记录澄清，不能改控制、原标签或仪器。

测量必须有COMPLETE.json且其中结果/审阅packet哈希正确，才能称输出完整。每例调用已运行的evaluate内部会把控制异常记录为execution_failure；测量层额外异常也明确记录，不自动补跑控制。结果已保存而审阅packet包装失败时，只可从既有结果确定性包装，禁止重做evaluate。语义组名称在首次测量前显式补充，与引用的原合同一致；之前协议快照及原仪器冻结记录保留。

合并：自动fail/execution_failure原样保留；review_required且语义conforms为本控制测量的hybrid_conforms，语义nonconforms为hybrid_nonconforms，indeterminate保持unresolved；自动pass为structural_conforms。没有任何结果代表生产准入。未知/失败单列，不能删除后只对成功例计算比例。作者参考与独立源码审阅有争议时列disputed，保留原参考计数另报争议，不强行计成仪器正确或错误。

## 预定验收与下一步

若32例中出现任何无争议正例被fail、负例被结构/混合判为conforms、或未解释execution_failure，则当前仪器不通过本批有限控制验收。全部匹配只表示通过这一小批控制，仍需更广合同/接口覆盖、未决状态政策、共同raw pool与成本核验；不直接宣称B完成。任何后续修复必须保留本次首测并使用新的未用于改动仪器的控制，不能把这批反例回归改名为独立校准。

模型只记录工具可见标识，更细后台构建版本unknown。应用内代理消耗不假称零成本。论文只有在科学范围和来源得到核验后才引用本批结果，不改写历史gate准入或benchmark数值。
