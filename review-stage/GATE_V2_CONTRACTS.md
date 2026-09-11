# Gate-v2：开发合同与独立裁决入口

版本：2026-09-10 development v1。**Release verdict: not ready**。
本文件定义尚未冻结的混合式仪器，不是已完成的 B 实验。旧 screening-v1 不改动；不根据新的 gate 结果替换旧准入或历史论文表格。没有运行新 benchmark、共同 raw pool 或收费 API。

## 1. 判断对象与状态

判断声明的行为是否有可观察证据，不能把“调用次数更多”“代码不同”“最后答对”当成机制成立。

- `pass`：当前有限结构探针通过；不是生产准入、语义正确性或科研放行。
- `fail`：至少一项具体结构或反事实合同未满足。
- `review_required`：需要独立语义裁决。不得当作拒绝、没有机制或已通过。
- `execution_failure`：异常、非法输出或探针调用上限中止；单独统计。

`hint_guard`、`format_guard`、`two_view`、`error_classify` 即使机械观察符合，也必须经过独立语义裁决。自动关键词、提示差异和模板差异只提供审查线索，不能证明指令语义或具体修复动作。该流程尚未获得独立裁决，因此不能用作新实验的最终准入 policy。

## 2. 八类可执行观察与待审内容

| 声明 | 自动观察和成对干预 | 拒绝/需复核的反例 | 剩余边界 |
|---|---|---|---|
| repair | 相同初始SQL，切换执行成功/失败；失败时携带精确错误到后续请求；相同初始SQL改变错误内容，输出须跟随；成功路径只有一个sample | 不执行、读取丢弃、无条件再调用、n=2批量偷加样本 | 目前主要覆盖首轮失败和两种错误载荷；最多两轮repair与持续失败边界须扩充独立fixture |
| vote3 | 三候选均被执行；改变排列与多数；固定ABC候选和顺序，只把执行结果多数设为AC/BC/AB | select-first、SQL字符串投票、固定首/尾tie fallback | 观察执行结果仲裁；不以温度/调用数证明采样独立性；失败/空结果/顺序与重复行规则须冻结扩展 |
| schema_link | stage1两种不同linked-subset载荷，实际传入后续请求且移除合成无关表 | 只调用不传递stage1、仍全量schema | marker传递不是一般SQL语义证明；仅当前合成schema/文字形式，不覆盖所有合法表达 |
| hint_guard | 无Hint/两种Hint；单sample；原问题和schema保留；Hint在原问题之外的显式要求中可见 | 纯透传、否定要求、复制原问题假装重述 | 全部需要独立裁决，允许合法单调用；不能靠词命中判PASS |
| two_view | 固定两SQL，只变执行结果为空/非空/失败；有两个请求，排除仅空白变化；两者都可用时选第一 | 忽略执行结果、同请求加空格 | 仲裁观察与“独立表述”语义分开；后者必须独立裁决 |
| decompose | 固定同一两步计划，改变不可由步骤名直接替换得到的partial-answer载荷；按序逐步调用，实际载荷进最终组装 | 只问不读、凭步骤名伪造答案、丢弃partial answers | 当前JSON两步计划是开发fixture输入，不是所有合法分解格式的验收全集 |
| error_classify | 成功不repair；syntax/schema/semantics各两种错误；精确反馈、单sample、单一显式类别及跨类动作模板差异 | 罗列全部类别、只改标点、两类共用同动作 | 模板差异不证明动作正确；类别含义/动作对应必须独立裁决 |
| format_guard | 原问题与schema保留；单sample；观察SQL fence/无额外文字要求 | 纯透传、明确要求不按fence输出 | 全部需要独立裁决；baseline若已经满足该策略，不因“不新颖”自动拒绝 |

这些合同是对声明的有限观察，不要求已有benchmark得分。探针均不读取gold；合成expected仅验证脚本化接口行为。正常轨迹未触发失败分支时只说明该路径未触发，不能据此认定机制无因果作用。

## 3. 独立语义裁决规则（待执行）

向不同于执行者的模型/审核者提供声明、完整问题/schema、全部solver请求、执行反馈、返回结果与源码证据。不能提供benchmark准确率或依据其修改结论。每例回答：

1. 所需观察是否存在，引用具体trace步骤与请求片段。
2. 要求是肯定、否定、冲突还是无法判断；是否保留原约束。
3. hint：是否把具体Hint当成硬约束；format：是否明确且无冲突地约束SQL输出和schema；two_view：是否确实有不同构造思路而非表面字符变化；error_classify：错误是否被正确分类，后续动作是否针对该类且语义合理。
4. 结论为 `conforms / nonconforms / indeterminate`，附证据，不强行二选一。

裁决记录须包含被审源代码与trace SHA256、contract版本、reviewer/model完整版本、独立于实现者的来源、时间和理由。审查不确定时保持待定；不得自行把模型内部机械复核当作跨模型独立裁决。必须预先冻结最终合并规则和人工/模型裁决预算，不能看到benchmark后改变规则。

## 4. 控制集与反例

`gate_controls.py` 的8个正控制和8个基础负变体由本轮同一执行者编写，仅作开发回归。两路代码复核又构造10个对抗反例：字符串投票两种tie规则、批量repair、类别全部罗列/只改标点/两类共用动作、空格视图、否定Hint、否定format、根据步骤名伪造partial answers。前两版误放轨迹保存在 `gate_v2_counterexamples_before_fix.json` 和 `gate_v2_counterexamples_round2.json`；它们是历史观测记录，当前回归运行以最终源码为准。

独立校准集尚未构造或冻结。当前没有可对外报告的独立误放率/误拒率。报告中的分类型状态计数只针对已用于开发和修改仪器的控制集，不能把review_required计为正确拒绝，也不能将通过率外推到生成种群。

## 5. 真实接口适配的范围

`gate_runtime_adapter.py` 用独立模块别名加载真实SQLHarness基类与受信本地控制源码；原始纯`extract_sql`函数按AST提取。solver/database由spy替代，不导入真实bridge配置、模型客户端或数据集初始化。已测试手写repair/vote、两个已知负变体及bare/format。

该适配器只支持受信本地代码、串行执行，不是安全沙箱。没有证明任意生成代码/辅助数据库接口均兼容，也没有恢复真实provider、缓存、数据库、judge的完整运行环境。首次将其用于raw pool前仍须完成接口覆盖和中断/超时处理。

## 6. 重放命令与B放行条件

```powershell
python -m unittest experiment.revision.test_gate_v2 -v
python -m unittest experiment.revision.test_gate_runtime_adapter -v
python -m experiment.revision.gate_development_report
```

第二、三个命令需要本地已恢复的TTHE控制源码；它们与无需external目录的统计重放不是同一层级。

B最终完成要求：完整合同和运行接口；独立正/负控制与四类语义裁决；分类型含待定状态的混淆矩阵；共同预生成raw pool、固定尝试上限及token账本；freeze SHA；在同pool上比较neutral/v1/v2；policy与固定K结果分开。**当前只完成开发探针和部分真实接口验证，以上放行条件尚未齐备。**
