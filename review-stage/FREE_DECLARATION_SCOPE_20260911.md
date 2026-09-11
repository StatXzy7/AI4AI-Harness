# Free声明与八策略gate的适用边界

2026-09-11，源码层审计；未读新候选内容，未执行候选、gate或benchmark。原始生成器及所有冻结规则不改。

## 可直接核验的差异

experiment/phase2/generate.py的DECLARE只提供repair/vote/twostage/plain四类。vote的原文是“you draw multiple samples and select among them”；它未写三次、temperature0.7或多数决。twostage只要求早期LLM产物被后期阶段消费；没有指定schema_link、decompose或其他八策略的具体接口。plain明确是single generation call, no control-flow mechanism，同时PROMPT_FREE正文要求real change to control flow，二者存在需要裁决的张力。

历史mechanism_pass将free声明传入conformance.run_scenario；conformance说明vote使用三个多数翻转场景。新版gate_v4的入口要求STRATEGIES八类，vote3复用v3；schema_link/decompose/error_classify又有指定profile。因此“八策略入口已统一”不等于free四类声明已得到同样明确、经过校准的处理定义。

## 后续共同池政策的约束

1. 保留free生成提示及原声明；不把vote静默改成vote3，也不从twostage中挑一个最易通过的八策略。声明缺失、存在多个声明或合同含混分别保留，不能强制当作机制不符合。
2. 原screening-v1按历史实现重放，可作为既有筛选政策；其通过/拒绝不能直接当语义真值。
3. gate-v4的八策略对照首先只具有forced八类的定义范围。free条件在四类合同和逐场景语义规则另行冻结、核验前保持未完成，不能合并形成完整S×G改进实验。
4. 即便free中某条源码显然属于某个八策略，也不能看哪个gate结果更好后再分配；若要源码指定profile，应先独立给出映射和歧义状态并绑定源码SHA，再运行所有预定场景。
5. “抽取语法有效”“neutral接口有效”“按旧政策准入”“声明语义符合”“独立任务有收益”保持不同字段。plain的合法性与free正文张力不能仅凭一个调用自动裁定；在合同未澄清前保留indeterminate。

## 结论边界

这是源文件中处理定义的适用性缺口，不是新候选上的误拒率，不证明历史全部vote或twostage都被错判。它也不撤销forced八类已保存的独立参考测量。B的forced范围和free范围必须分别验收；共同raw pool完成本身不能补上此缺口。A/C/D仍需独立结果，论文整体评分不变。
