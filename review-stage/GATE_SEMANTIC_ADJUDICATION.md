# Gate-v2：14例开发材料的不同模型语义裁决

2026-09-10。完成的是开发集的独立语义审阅；Gate-v2 release和B实验仍not ready。开发执行模型为GPT-6，裁决模型为gpt-5.5，服务端更细构建版本不可见。不同模型来源符合项目分工，但不能据此假设二者错误统计独立，也不是专家共识。

## 审阅边界与固定规则

审阅前固定`artifacts/revision_20260910/gate_semantic_adjudication/DECISION_RULE.md`。审核者仅接收规则、原合同第1至3节和无预期标签的14例packet；不接收开发报告标签、gate实现或benchmark成绩。该packet的函数名称已匿名化，但控制源码和合成轨迹可见；这是隐去标签的开发集审阅，不是随机盲法试验或未曝光校准集。

每例记录源码/轨迹SHA256、`conforms / nonconforms / indeterminate`、理由、probe和证据字段。初稿原字节保存在`adjudication.initial.json`；一次允许的澄清将字面转义换行及执行字段摘要改为可逐字或逐字段核验的证据，裁决不变。审核者没有读取benchmark或发出外部模型API请求。应用内代理消耗不报告为零成本。

## 开发集裁决分布

| 类型 | 例数 | conforms | nonconforms | indeterminate |
|---|---:|---:|---:|---:|
| hint_guard | 3 | 1 | 2 | 0 |
| format_guard | 3 | 1 | 2 | 0 |
| two_view | 3 | 1 | 2 | 0 |
| error_classify | 5 | 1 | 4 | 0 |
| 合计 | 14 | 4 | 10 | 0 |

符合的四例分别明确表达额外Hint硬约束、SQL格式/schema要求、join与subquery两种构造并依据执行结果仲裁、错误类别对应不同合理修复动作。结论针对请求与控制路径表达的语义，不证明脚本solver遵从、SQL真实正确或两次采样独立。

不符合的例子包括：透传原问题而不表达新增要求；忽略Hint或否定SQL格式要求；双视图永远取首结果或仅加空格；普通repair冒充错误分类；罗列全部类别、仅改变标点或给schema错误同样的语法修复动作。

## 与原结构判决合并

原结构探针中8例为review_required、6例为fail。按照发送材料前固定的规则：8例待审项成为4例`development_semantic_conforms`和4例`development_semantic_nonconforms`；另6例保留结构fail并附语义nonconforms。原报告、源码和历史准入不改写，所有状态均不自动转为生产PASS。

这14例已经参与过开发或对抗回归。上述分布不能称误放率/误拒率；四类各有一例符合也不证明合法实现全集被覆盖。独立构造、未用于改动gate的控制集及冻结后的分类验收仍待完成。

## 对B实验和论文的实际推进

先前“所有四类语义尚无独立裁决”的开发待办，本批14例已完成；“对新候选或独立校准集的语义裁决已完成”仍不成立。下一步是独立正负控制、完整真实接口覆盖、预定合并政策与校准，再到共同raw pool的neutral/v1/v2比较。共同raw pool、固定尝试与成本记录、policy/fixed-K结果均不能由本表替代。

本轮未修改论文实测数字、英文/中文源码或PDF。论文仍需A稳定能力与clone/资源匹配、B校准与raw pool、C桥接、D独立效用和W1正式推断，整体沿用原审稿4/10、not ready。

证据入口：`artifacts/revision_20260910/gate_semantic_adjudication/verification.json`；逐例裁决与合并表在同目录。原合同`GATE_V2_CONTRACTS.md`保持原哈希，本文件作为阶段17状态补充，不能把旧开发验证文件改称独立校准通过。
