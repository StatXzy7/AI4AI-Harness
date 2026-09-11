# 阶段24：归档候选接口诊断

本轮完成七份真实SQLHarness候选的27个合成场景，未进行模型调用或benchmark评测。冻结v3给出10个结构pass、4个fail、13个review_required，无执行异常；另有1条跨类别派生审查记录，不计独立场景。format_guard没有既有可调用候选，保持缺失。这些计数是仪器观察，不是准入率、误拒率或八类校准结果。

来源为阶段22已固定的每类词典序第一份C候选，全部来自DeepSeek，是确定性的接口样本，不代表六builder生成种群。未因失败改选候选，未改旧源码、gate-v3或adapter。执行前协议为RUNTIME_GATE_DIAGNOSTIC_PROTOCOL.md；原始逐类记录及COMPLETE位于`artifacts/revision_20260910/runtime_gate_bridge/stage24/`。

| 策略 | 场景数 | 本次观察及可解释范围 |
|---|---:|---|
| repair | 3 | 成功路径1次solver/1次execute；两失败路径均2次solver/2次execute，精确反馈进入修复，有限结构检查通过。未覆盖持续失败或两轮用尽。 |
| vote3 | 6 | 每次n=3并执行3份，随排列/执行结果多数变化选择；有限结果仲裁检查通过，不证明模型采样独立。 |
| schema_link | 2 | 两次均回退全schema。首回复为普通`ledger(id) [marker]`，候选要求tables/columns JSON；当前fail不能识别合法JSON输入下的机制。源码还按CREATE TABLE提取DDL，而实际schema_text输出Table行，需在正确JSON输入下另行定位。 |
| hint_guard | 3 | 单次solver，原问题/schema保留；两个Hint分别进入额外硬要求。机械观察符合，语义判断须结合完整指令。 |
| two_view | 4 | 首个空/失败时执行两份；首个非空的second_empty与both_nonempty中只执行第一份。生成提示分别要求JOIN和subquery，选择输出符合first-nonempty，但少执行第二份违反原声明的execute both。 |
| decompose | 2 | 均4次solver/2次execute。子问题请求含完整计划和明确Current sub-question字段，v3只看到多个未回答步骤，返回UNRELATED；这是探针归属限制，不能用最终UNRELATED证明候选丢弃真实子答案。 |
| error_classify | 7 | 成功不修复；6失败场景均携带错误并修复。合成syntax/schema failure不匹配本地SQLite错误短语，均走semantics默认分支。该观察不能建立真实SQLite错误分类准确率；需要真实错误措辞及动作消费的独立检查。 |
| format_guard | 0 | 既有C候选缺失；不使用合成文件补作历史候选。 |

原始two_view生成要求位于`experiment/phase2/generate.py`的STRATEGIES；当前候选的早返回位于`p2_C_deepseek_s0_two_view.py::solve`。因此这是可定位的候选合同偏差，不能仅以最终SQL符合预期放行。schema_link和decompose则首先存在响应格式/归属接口问题，不能与这项偏差混为同类。

下一步修复应针对可测性：schema-link使用独立源码确认的响应格式和实际Table schema，保留JSON失败与有效JSON两种情况；decompose从完整请求识别明确目标并保留歧义，不按预期答案替代归属；error-classify用可追溯SQLite错误输入测试本地分类和相应动作。新增组件必须保留本次固定v3观察，不通过改同一结果实现“通过”。这些是后续接口工作，当前尚未实现或独立校准。

本阶段论文/PDF沿用阶段22，未新增总体效果结论。B仍不具备完整接口/独立校准/共同池比较，A重复与clone、C受控桥接、D独立效用及W1正式推断也未闭环；论文整体仍not ready。源文件、结果与前阶段证据的精确绑定见本阶段verification.json。

机械审核9/10 ready，2项既有适配器测试及Ruff通过。跨模型合同初审8.8/10 almost要求完成标记绑定manifest；该项在执行前修复。gpt-5.6-sol随后独立审阅全部27场景及源码，给出9.4/10 ready，仅限诊断证据与解释边界；确认two_view合同偏差，schema_link/decompose/error_classify保持接口限制下未决。逐条证据在independent_review.json，所有引用由执行者再次回指核验。软件分数不转换为论文评分。
