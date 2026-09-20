# 中文稿同步状态：2026-09-21

> 本次已同步至英文投稿源 `paper/latex/main.tex` 的 2026-09-20 定稿稿（新标题《Diagnosing Apparent Complementarity in AI-Generated Harness Populations》）。阅读入口：[中文 PDF](main.pdf)、[英文 PDF](../latex/main.pdf)。这是作者参考译本，不用于投稿或英文页数验收。

编译结果：全文 32 页，正文结束于第 11 页（英文全稿 25 页、正文 9 页）。`xelatex` 三遍 + `bibtex` 零错误、零未解析引用、零缺字；仅有已知的宋体 small-caps 字形回退（与旧版一致）与 1 个 overfull box。中文 TeX 文件均为 UTF-8。

## 本次同步的主要内容（相对 2026-09-12 旧中文稿）

- 标题、摘要全部重写：五类命题（测量充分性、单次覆盖、稳定排序、稳定互补性、执行前可选择性、预算匹配效用）。
- 新增正文第 6 节「表观互补性的校准诊断」（`sec_diagnostics.tex`），含 $H_{\rm stable}$ 恒等式、交叉拟合冻结选择增益 $G$、真实减克隆差 $D$、已知真值校准表（表 5，共用英文 `calibration_table.tex`）。
- 新增正文 §5.4「MATH-500 上新的克隆控制证据」（`sec_wp1r.tex`）：$G_{\rm real}=0.17$ pp、$D=-0.10$ pp（CI $[-1.55,1.46]$，$p=.7742$）、覆盖门控失败、共同预算表（表 4，共用 `revision_budget_table.tex`）、E3 选择器结果。
- 新增附录 I「WP-1R/WP-2R 新采集：协议与执行记录」（`sec_app_wp1r.tex`）：冻结协议、v3 统计程序、续跑合并、预算语义与已实现账目、$\pi_Z$ 规格、比较器表（表 12，共用 `wp1r_policy_table.tex`）。
- 附录新增 H「诊断流程与验证」（在 `sec_appendix.tex` 内）：五类形式定义、两个稳定性估计目标、v3 判定、零假设族规模论证、并列处理、随机化机制、模拟校准网格、有限重复偏差、D/E 形式定义、人工控制验证、在 BIRD/MATH 存档上的应用（含 14 次翻转、288,104 次调用等）。
- 引言改为四条贡献并加入 MATH-500 结论段；相关工作补 HarnessForge、gail-simon、caruana、self-consistency、pass@k 等引用与表述。
- Phase I/II、结果、讨论、结论、跨领域附录均逐段对齐英文定稿：共同尝试上限（最多三次、首次接纳即停）、II-E 描述、R2/R3 数字（2391/28,000、14.5%）、MATH 33/36 唯一向量与 0.6825–0.915 准确率区间、14,400 判定中 14 次翻转等。
- main.tex 新增致谢、伦理声明、可复现性声明的中文译文；AI 使用声明对齐英文现稿。
- 数值宏同时 input 英文共同源 `revision_numbers.tex` 与 `wp1r_numbers.tex`；新增表与图直接共用英文产物，表内英文标签按旧例保留，不另做手工数值表。

## 维护约定

- 正常入口为 `latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex`（在本目录执行）。
- 本机遇到 XeLaTeX 轮次争用 main.log 时，分次执行：
  `xelatex -no-pdf ... main.tex` → `bibtex main` → 再两遍 `xelatex -no-pdf` → `xdvipdfmx -o main.pdf main.xdv`。
- 修改英文稿后，按文件对照更新本目录同名（或新增）章节；数字、表格、图不要手抄，一律引用 `../latex/` 共同源。
- 重新构建会改变 PDF 哈希；如需验收快照须重新记录哈希，不能以旧快照冒充新构建。
