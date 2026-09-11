# 阶段26：统一Gate-v4及已曝光回归

Gate-v4现在通过同一evaluate入口覆盖八类策略：五类直接复用冻结v3场景；schema_link、decompose、error_classify合并源码指定回复接口，分类同时支持本地分类及中间LLM类别回复。未知profile保持待审且不执行，不能当作候选不符合。三个typed类型全部保存待审轨迹，不自动准入。原始gate、候选、旧校准结果保持。

schema-link不再把完整schema上下文存在当作自动拒绝理由；需要审查关联载荷是否实际约束后续请求。分解使用专用当前目标与实际SQL载荷。分类在真实SQLite错误后才请求或注入类别，支持syntax/schema及整数溢出的残余执行错误场景；LLM类别路径另有无效/歧义诊断。整数溢出不代表识别答错；正确类别注入不测模型分类准确。类别到动作的含义仍须独立裁决。

## 本轮证据

8项相关测试及Ruff通过。机械审核9/10 ready，gpt-5.6-sol合同复核9.4/10 ready（执行者GPT-6），均只覆盖开发代码和合同。固定名册的7份归档候选、1项缺失、2个旧负控及1个旧开发format控制共完成39个场景，无执行异常；没有更换失败样本。

| 对象 | 场景数 | 结构结果 |
|---|---:|---|
| 归档repair / vote3 | 3 / 6 | pass / pass |
| 归档schema_link / hint_guard | 3 / 3 | 待审 / 待审 |
| 归档two_view | 4 | fail；首个非空后仍少执行一份 |
| 归档decompose / error_classify | 2 / 7 | 待审 / 待审 |
| 归档format_guard | 0 | 不可用；不补造 |
| 旧无条件额外调用 / 固定选首负控 | 3 / 6 | fail / fail |
| 旧format开发控制 | 2 | 待审；保留合法单调用路径 |

这些结果没有把真实schema/decompose/classification自动升级为符合；也没有把仍失败的two_view或两个负控放过。LLM分类9场景的代理顺序由合成测试验证，本次归档分类候选采用源码决定的本地分类profile，未通过尝试两种profile择优。旧32例参考并未在本次重新测量，不宣称覆盖全部旧反例。

产物为`artifacts/revision_20260910/gate_v4_regression/`：manifest绑定源码/候选/profile/协议/Python/SQLite；COMPLETE绑定manifest/results；instrument_freeze仅冻结独立参考检验所需开发仪器，不是provider或科学实验授权。不要覆盖或重跑首批39场景来改变记录。后续改动必须保留该版本。

下一步是在该冻结入口上独立构造并静态核验新参考，明确每类至少两符合/两不符合、typed三类的语义合并规则及未决处理，再执行一次完整校准。响应格式支持范围仍有限，持续修复失败等边界待补齐。完整共同pool、policy/fixed-K、A/C/D及W1仍未完成；论文整体not ready。本轮论文/PDF沿用阶段25，无provider或benchmark调用。
