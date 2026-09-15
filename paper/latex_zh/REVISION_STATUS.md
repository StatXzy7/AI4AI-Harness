# 中文稿同步状态：2026-09-10

> 注意：这是作者参考译本，对应 2026-09-12 前的英文工作稿。当前投稿英文源已更新为 `paper/latex/main.tex`（2026-09-15 insight 稿），中文尚未跟进。

已同步当前英文工作稿的完整正文、AI 使用声明与全部附录。阅读入口：[中文 PDF](main.pdf)、[英文 PDF](../latex/main.pdf)。这是作者参考译本，不用于投稿或英文页数验收。

本次译本共19页，正文结束于第11页；英文全稿16页、正文9页。十个中文TeX文件均为UTF-8无BOM。正文/附录与英文使用相同引用键和标签。为避免统计数字漂移，35个数值宏、6张结果表、3幅图和参考文献直接读取英文共同源；图表内部英文标签与参考文献原文保留，不另做手工数值表。

主要同步内容包括：主对比−0.16 pp，95% CI [−0.83,+0.87]；旧gate排除两类提示策略；最多三次尝试且首次接纳即停；K-matched与R2的不同bare范围；逻辑调用不等于计费请求；W1/W3的canonical描述性重算、撤回旧CI及稳定互补性仍未识别。gate-v2开发与设计模拟未写成论文新实验。

同步时也修正了英文残留矛盾：相同源码不保证随机执行结果相同；正观测headroom不是稳定路由信号；Phase-I代理评分器与Phase-II官方评分器分别披露；数据库图表补18题冒烟例外；SQL实例区分直接计数与连接后计数，不声称去重计数；模型清单的采集窗口限定为BIRD。相关工作压缩重复定位，保留所有引用和限制。

验证记录：[chinese_sync_verification.json](../../artifacts/revision_20260910/chinese_sync_verification.json)。记录中英文源码、共同构建输入及两版PDF的SHA256。编译无未解析引用、缺字或overfull；全页缩略检查和主要结果/附录页面放大检查通过。Windows已安装宋体等CJK字体；宋体无small-caps字形时回退普通字形。机械依赖复核9/10 ready，译本语义复核10/10 ready，均只覆盖本轮交付，不是独立跨模型论文评分。

正常入口为 `latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex`（在本目录执行）。本机遇到连续XeLaTeX轮次争用main.log时，可分次执行以下命令，每条完成后再执行下一条：

```powershell
xelatex -no-pdf -interaction=nonstopmode -halt-on-error -recorder main.tex
bibtex main
xelatex -no-pdf -interaction=nonstopmode -halt-on-error -recorder main.tex
xelatex -no-pdf -interaction=nonstopmode -halt-on-error -recorder main.tex
xdvipdfmx -o main.pdf main.xdv
```

重新构建会改变PDF哈希，须重新检查并更新验证记录，不能以旧快照冒充新构建验收。

整体研究仍为not ready。外部审稿起始评分4/10尚未重新独立评定；A–D正式实验、独立效用和最终投稿验收仍待完成。任务入口：[修订状态](../../review-stage/REVISION_20260910.md)、[实验计划](../../review-stage/REVISED_EXPERIMENT_PLAN.md)。

## 稳定识别补充修正

当前PDF已同步`STABLE_IDENTIFICATION.md`对应措辞：超过发现阶段选定的次优固定成员不足以证明稳定互补。实测数字不变，英文正文仍9页，中文全文19页；受影响页重编译和检查完成，最新哈希仍见`chinese_sync_verification.json`。这项数学/措辞修正不代替A–D实验。


2026-09-10阶段13：AI使用声明同步更正，披露同模型机械复核及AI参与研究设计的实际范围；作者最终责任不变。英文16页/主文9页，中文19页/正文止于11页。实测结果未改；当前SHA见chinese_sync_verification.json；旧稿及验证在before_ai_disclosure归档。
