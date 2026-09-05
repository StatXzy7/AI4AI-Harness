# Prompt-1 修订交付报告 — 2026-09-05

**修订对象:** paper/latex(全部正文章节重写或修订)
**构建产物:** paper/latex/main.pdf — 12 页(主文 9 页),sha256[:16] `1988c3f162ae629b`
**构建命令:** pdflatex → bibtex → pdflatex ×2(pdfTeX, TeX Live 2026),独立 build 目录,exit 0
**验证:** 0 LaTeX error、0 undefined citation/reference、17 条参考文献全部渲染、无 `(?)`、
无作者/机构泄露、匿名页眉 "Under review as a conference paper at ICLR 2027"

## 已修复(对照审计条目)

| 审计项 | 处置 |
|---|---|
| P0-1 撤回证据链(40 bare 副本 / 780/780) | 摘要/引言/正文/结论全链移除;重写为 M0 generation-null 独立报告段(§3.6),collapse 主张仅保留在真正不同源码的 day-1 群体;全文 grep 验证 780/builder-independent 零残留 |
| P0-2 方法脱节 + A/B/C/D 一名两义 | 新结构 §3=Phase-I discovery(条件用描述性名称)、§4=Phase-II(臂名 II-A/B/C/D/E + 因子定义);摘要与引言明确两阶段边界;Phase-I 三重局限(nested contrasts、无日志预算、smoke≠gate)在 §3.5 与附录 A 如实陈述 |
| P0-3 构建错误 | `bibliographystyle` 2026→2027(main.tex:88);全部 longtable+`LTcaptype` hack 改为带编号 caption 的 `table`/`tabular`(`No counter 'none'` 清零);干净 4-pass 构建 |
| P1-1 headroom 数学 | §4.2 更正:单调的是 oracle accuracy;给出反例(加一个全对 harness 使 headroom→0);matched-K 作为控制手段而非单调性推论。Discussion 撤除"未过 checklist ⇒ 至多找回最佳固定"(改为:4pp 群体仍可能支持优于固定选项的 routing;checklist 是测量约定不是定理) |
| P1-2 因果措辞过强 | "gate without a capable builder produces nothing" 删除;D−A 明确表述为组合干预,gate 主效应/交互归 core-400 四臂分析;"deployment-relevant success" 改为"narrow",声明任务重叠、非部署保证、单 builder 池有 2.8%/8.7% 干预 harm |
| P1-3 新颖性笼统排除 | "first systematic / none measures" 移除;新增最近邻对照表(研究单位/population collapse 测量/门禁定义/校准/因果隔离/确认性 split 六维)区分 HarnessLens 与 HarnessBank |
| 阅读体验 | 标题缩短为一行(修 Diver-sity 断词);摘要 302→212 词;主表改紧凑 table;`Section 6.0b`、错误附录引用、B/B3 重复行、"Rows 7–9"错位、7→7.1 重复标题、"two nested contrasts, originally"、pre-registration 措辞——全部清除(相关文件重写) |
| 图接入 | Fig.1 现象图(p4,14 harness/91 对/ρ=−0.01,图注含样本量、阶段、来源、pair 非独立性声明);Fig.2 设计图(p7);双口径(66 候选对 vs 91 全群体对)在 §3.2 与图注中并列说明 |
| PAPER_PLAN | 重写为 v3;历史状态文档标注为快照 |

## 待数据(不可在本轮完成)

1. **§5 全部结果**(主表/因子表/可靠性表/审计):表结构已定,全部 pending 占位;
   未用任何 Phase-I 或 partial 数字回填;完成条件 = 提示词二完整性验收通过。
2. **摘要/引言中的 Phase-II 定量占位**:引言只写设计不写预期方向;结论三种条件式草案已备。
3. **R2/R3 审计结果**入附录(采集完成后运行 `run_audits.sh`)。
4. **AI use statement 事实核实**:"人类作者作出全部方向性决策"等表述已交由作者本人核实
   (Agent 不代作保证),该责任声明句已加入声明末尾。
5. **analysis_primary.py 文档不一致**(first-write-wins vs last-write-wins,冲突检查只看
   official_correct):已列入提示词二的跨模型验收范围,本轮不改分析代码。

## 保留不动

- 冻结协议 `PHASE2_PROTOCOL.md` / `PROTOCOL_FREEZE.txt`(仅被引用,未修改)
- 正在运行的采集进程与其输出文件(未触碰)
- Phase-I 全部实测数字(以 discovery 身份保留,含记录缺口披露)


## 复审修订(2026-09-05 第二轮,Codex 6.8/10 almost 的 9 项阻塞全部处置)

| 阻塞项 | 处置 |
|---|---|
| B1 相关性表述过强 + 图内 p 值 | 摘要/引言改为 "no observed rank association";fig_phenomenon 重新生成,标题仅 ρ(无 p);清单加 C13 |
| B2 双口径未标注度量差异 | §3.2 明确 0.143=归一化字符度量(原始检查)、0.190=token 度量(图);摘要标注 91 对含 baseline;3.5%→3.3% 与图一致 |
| B3 新颖性笼统 + HarnessLens 误述 | 删除 "none measures";HELIX 明确承认其测过 65 候选 outcome matrix;对照表 HarnessLens 门禁改为 attributable-evidence + gate ablation(single factor) |
| B4 pending 状态 + 冻结历史限定 | 摘要加 "data collection is ongoing";§4 开头披露 D1 18-item smoke 例外;"never-opened" 改为 "never opened during development" + registry 范围限定 |
| B5 条件式结论不对称 | near-zero 分支改为 "no clear improvement (CI overlapping zero)" + "未解决估计不等于无效应证据";负向分支要求 CI 排除零 |
| B6 摘要控制字符 + 图重叠 + Phase 标签 | 修复 `	`imes/``ho 字节损坏(git-bash heredoc 转义根因);fig_design v2 重排(E 臂独立、admission 全宽底行、Phase-I 151/Phase-II 365 分开标注) |
| B7 AI 声明代作保证 | "were reviewed by them" → "provided for author verification; final responsibility rests with the authors" |
| B8 参考文献元数据 | BIRD 作者改会议记录形式(Jiaxi Yang/Binhua Li/Ruiying Geng);TTHE 补 Xinmei Tian、Bo Han + and others;验证注释改为准确表述(14 API 核实 + 会议记录) |
| B9 清单不忠实 | C1 改 discovery-only + 双度量标注;C3 删 14.9%;C6→§6;C8→§4.2/§5.2;新增 C12(第二 target)、C13(相关性措辞) |

**修订构建:** 12 页(主文 9),exit 0,0 error,0 undefined;main.pdf sha256[:16] = `6b8504addc60ec77`
**分页更正:** Figure 2 在 p6;AI 声明 p9–10;参考文献 p10–11;附录 p11–12(总页数与主文上限不变)。
