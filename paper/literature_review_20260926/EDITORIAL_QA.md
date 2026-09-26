# 中英文主文写作检查

检查日期：2026-09-26。检查方式：只读英文与中文 `main.tex` 及 `sec_intro`、`sec_related`、`sec_phase1`、`sec_setup`、`sec_phase2`、`sec_selection_design`、`sec_coverage`、`sec_results`、`sec_utility`、`sec_supporting`、`sec_discussion`、`sec_conclusion`，共 26 个源文件。附录仍在编辑，本轮未检查；PDF 排版与编译由主任务核验。

**初检写作质量：score 8.5/10；verdict：almost。** 该评分只评价本轮阅读中的表达与组织，不预测学术接收或评审分数。修订后的最终结论见文末关闭记录。

主线已经形成连续阅读路线：程序与重复的分配问题，覆盖现象，同代码参照，重复结果，实际选择，执行案例，最后回到设计经验。结果标题提供了明确发现，选择器零收益被直接陈述为已完成结果。中英文的主要数字、方向与结论一致，没有发现需要整段重写的翻译偏移。值得调整的内容限于以下四处。

## 1. 删除将两项结果写成因果关系的连接词

位置：[英文 discussion，第 8 行](E:/projects/AI4AI-Harness/paper/latex/sec_discussion.tex:8)；[中文对应段，第 2 行](E:/projects/AI4AI-Harness/paper/latex_zh/sec_discussion.tex:2)。

英文在持续失分的描述之后使用 `consequently` 引出冻结选择器结果，读者可能理解为前者已解释了后者的原因。中文对应句没有这一因果词，因此英文比中文多了一层推断。这里两项结果并列已经足够推进故事。

建议：删除 `consequently`，保留 *The frozen selector provides a direct practical result...*。这是逻辑连接与双语对齐的局部修订。

## 2. 让未判清的结论由留出比较承担，校准说明灵敏度

位置：[英文 discussion，第 21 行](E:/projects/AI4AI-Harness/paper/latex/sec_discussion.tex:21)；[中文对应段，第 5 行](E:/projects/AI4AI-Harness/paper/latex_zh/sec_discussion.tex:5)。

`Three-repeat calibration leaves stable complementarity unresolved` 与中文“三次重复的校准尚未判清稳定互补性”把校准写成了作出实证结论的分析。前文已经清楚区分留出比较与已知真值模拟；讨论继续沿用这一分工会更准确，也更容易读。

建议：*With three repeats, the held-out comparison leaves stable complementarity unresolved; calibration illustrates the diagnostic's limited sensitivity.* 中文同步写为“三次重复的留出比较尚未判清稳定互补性；校准说明了该诊断的灵敏度限制。”不增加新的技术说明。

## 3. 压缩摘要末尾重复的三属性说明

位置：[英文摘要，第 48 行](E:/projects/AI4AI-Harness/paper/latex/main.tex:48)；[中文摘要，第 28 行](E:/projects/AI4AI-Harness/paper/latex_zh/main.tex:28)。

摘要开头已经交代 coverage、repeatable performance 与 usable selection，末尾又用三项并列重新说明，接着才给最终解释。摘要并不长，但这一重复让收尾多停了一步，削弱 programs/rolls 问题的回扣。

建议：压缩或删除 *Together, these findings distinguish three properties...can use* 这一句，保留随后“持续差异主要揭示失分，而额外基线执行匹配完整预算覆盖”的结果解释。中文对应压缩“这些发现区分了程序群体的三种性质……”一句。这样无需增加数字或改变结果，就能让摘要更快落到答案。

## 4. 给 T1 中的 artifact 一个具体对象

位置：[英文 supporting，第 20 行](E:/projects/AI4AI-Harness/paper/latex/sec_supporting.tex:20)；[中文对应句，第 8 行](E:/projects/AI4AI-Harness/paper/latex_zh/sec_supporting.tex:8)。

`execute no artifact` 与“不执行产物”没有告诉读者产物指生成 SQL、外部代码，还是某一机制。这一小节本来依靠具体行为帮助理解，因此这里的抽象名词会打断阅读。中英文均有同一问题。

建议：沿用现有轨迹事实明确对象；若这里指返回前没有执行生成 SQL，就直接写出 SQL。也可以直接说明没有实现对应检索或自检步骤。无需展开完整轨迹。

## 对综合风格报告的复核

[STYLE_REPORT.md](E:/projects/AI4AI-Harness/paper/literature_review_20260926/STYLE_REPORT.md)所列 38 篇正式会议样本、2 篇 TMLR、1 篇单列预印本，以及 10 份企业原始报告，与分组记录一致。企业文档分类为 7 份技术报告、1 份 model card、2 份 system card；报告明确区分目标章节精读与逐页通读，也没有将 Oral、奖项或引用数解释成数值评审分。

本轮只创建本检查报告，没有修改论文源文件。以上行号对应检查时的已汇合正文；后续编辑可能改变行号。

## 四项修订关闭记录

2026-09-26 复核仅覆盖上述四项的中英文实际源文件，没有扩大检查范围。四项均已关闭：

| 项目 | 复核结果 | 当前定位 |
|---|---|---|
| 1. 因果连接 | 英文已删除 `consequently`，与中文并列叙述一致 | [EN discussion:8](E:/projects/AI4AI-Harness/paper/latex/sec_discussion.tex:8)、[ZH discussion:2](E:/projects/AI4AI-Harness/paper/latex_zh/sec_discussion.tex:2) |
| 2. 未判清结论的主语 | 两种语言均由三次重复的留出比较承担结论，校准不再充当主语 | [EN discussion:20](E:/projects/AI4AI-Harness/paper/latex/sec_discussion.tex:20)、[ZH discussion:5](E:/projects/AI4AI-Harness/paper/latex_zh/sec_discussion.tex:5) |
| 3. 摘要重复 | 两种语言均删除末尾重复列举三属性的句子，保留结果解释 | [EN main:48](E:/projects/AI4AI-Harness/paper/latex/main.tex:48)、[ZH main:28](E:/projects/AI4AI-Harness/paper/latex_zh/main.tex:28) |
| 4. T1 具体对象 | 两种语言均明确为未实现所描述的检索或自检步骤 | [EN supporting:18](E:/projects/AI4AI-Harness/paper/latex/sec_supporting.tex:18)、[ZH supporting:8](E:/projects/AI4AI-Harness/paper/latex_zh/sec_supporting.tex:8) |

**最终仅写作 verdict：ready；score 9/10。** 本轮指出的四项表达问题已落实，未有待关闭的编辑项。该结论只覆盖已阅读主文及本次四项复核，不代表学术接收预测、实验验收或 PDF 排版验收。
