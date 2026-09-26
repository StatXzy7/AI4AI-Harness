# 2026-09-26 写作风格调研与全文改写

已完成 38 篇正式会议论文与 10 份企业报告的写作风格调研。另单列 2 篇 TMLR 论文和 1 篇预印本。22 篇会议论文完成指定章节的结构精读，10 份企业报告均有定点阅读；21 个来源保留了 2026-09-26 Semantic Scholar 引用量快照。原始评审分没有完整核实，荣誉、展示形式与引用量分别记录。

调研以用户已人工复核的研究定位为前提，提炼叙事与表达方法。企业样本覆盖 OpenAI、Anthropic、DeepSeek、GLM 与 Kimi。来源总表与逐篇阅读锚点均可回查。

## 阅读入口

- [综合风格报告](E:/projects/AI4AI-Harness/paper/literature_review_20260926/STYLE_REPORT.md)
- [51 个来源的统一索引](E:/projects/AI4AI-Harness/paper/literature_review_20260926/source_registry.csv)
- [英文修订稿](E:/projects/AI4AI-Harness/paper/latex/main.pdf)
- [中文同步稿](E:/projects/AI4AI-Harness/paper/latex_zh/main.pdf)
- [写作 QA 与修正记录](E:/projects/AI4AI-Harness/paper/literature_review_20260926/EDITORIAL_QA.md)
- [机器核对记录](E:/projects/AI4AI-Harness/artifacts/story_style_rewrite_20260926_161326/validation.json)

## 本轮改写

共改写 44 个 LaTeX 文件，即中英文各 22 个。摘要和引言以预算分配问题开篇，按覆盖、重复行为、实际选择逐步展开。方法先说明操作目的，再给定义和公式；结果以发现开头，随后呈现代表性数字和解释。讨论回到开篇的决策问题。

附录整理为技术查阅材料：保留配置、公式、完整表格与实例，压缩重复限定、修订过程和内部操作记录。AI 使用声明合并为一个集中段落。结果解释所需的条件保留在相应方法、结果或简短适用范围中。

## 实测篇幅

| 项目 | 改写前 | 改写后 |
|---|---:|---:|
| 英文全文页数 | 25 | 22 |
| 英文正文末页 | 8 | 8 |
| 中文全文页数 | 30 | 26 |
| 中文正文末页 | 10 | 9 |
| 英文文本、标题、图注词数 | 9604 | 7559 |
| 9 个改写附录文件的对应词数 | 5305 | 3769 |

英文计数使用 `TeXcount -inc -sum=1,1,1,0,0,0,0`，含正文文本、标题和图注，不含参考文献及数学表达式计数，数值宏不作展开。页数取实际 PDF；正文末页来自 `endofmain` 标签。中文为参考译本。

## 核对结果

- 两个入口均编译成功，无未定义引文、交叉引用或越界盒警告。
- 20 个受保护的数值、表格及文献文件 SHA-256 不变。
- 44 个改写文件的 label、引用键及次数、tabular 内容逐项一致；中英文结果宏次数一致。
- 附录表图和原始引用轨迹整块不变，具体记录见同目录快照内 `appendix_style_checks.json`。
- UTF-8 中文无替换字符；英文全部页面及中文全部页面已渲染检查，修复中文附录导航跨页。中文编译存在小型大写字体回退提示，已检查其可见文本显示正常。
- 写作 QA 四项意见均已修复，最终 **score 9/10，verdict ready**。该评分仅评价表达与结构。

改写前后快照、逐文件差异、编译日志和页面渲染保存在 [版本目录](E:/projects/AI4AI-Harness/artifacts/story_style_rewrite_20260926_161326)。`before/` 保留本轮开始时的文件，`after/` 固定本轮交付版本。
