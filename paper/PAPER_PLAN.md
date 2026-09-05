# PAPER_PLAN — v3 (2026-09-05, prompt-1 revision)

> 本文件取代 2026-09-02/03 版本(该版含旧 GLM 0/6、旧 task split、已完成 LaTeX 化等
> 过期状态,已被本轮修订超越)。有效协议入口:`PHASE2_PROTOCOL.md` +
> `PROTOCOL_FREEZE.txt`。状态文档:`review-stage/CLAIM_EVIDENCE_20260905.md`(主张-
> 证据清单)与本文。

## 当前论文状态(prompt-1 修订完成)

**标题:** Behavioral Collapse in AI-Generated Harness Populations(短标题,修复断词)
**主文:** 9 页(§1–8),共 12 页(AI 声明 p10 不计页限、参考文献 p11、附录 p12)
**构建:** pdfTeX TeX Live 2026;exit 0;0 LaTeX error;0 undefined citation/reference;
main.pdf sha256[:16] = `1988c3f162ae629b`

## 结构(问题→测量与诊断→Phase-II 设计→结果→边界)

| § | 内容 | 状态 |
|---|---|---|
| 1 | Introduction:前提失败 + M0 分离 + Phase-II 预告;贡献 3 条(无 "first systematic" 笼统声明) | ✅ |
| 2 | Related Work + 最近邻对照表(HarnessLens/HarnessBank:研究单位/是否测 population collapse/门禁定义/校准/因果分离/确认性 split) | ✅ |
| 3 | Phase I discovery:三指标 + 塌缩量化(双口径并列)+ T1–T3 + 人工对照 + 协议探针及其三重局限 + M0 报告 | ✅ |
| 4 | Phase II 设计:II-A/B/C/D 因子臂 + II-E、等预算 R=3、6 builders × 3 seeds、数据隔离、官方 judge、仪器校准、冻结分析计划 | ✅ |
| 5 | Phase II 结果:三张表骨架,全部 **pending**(未用任何中间数字回填) | ⏳ 等采集 |
| 6 | 边界结果:LOHO 负结果,严格限定到已测 predictor/split;+6.9pp 收窄表述 | ✅ |
| 7 | Discussion:headroom 非单调(反例)、checklist 非定理、可靠性/质量分解 | ✅ |
| 8 | Conclusion:三种条件式结论草案(正/零/负),按冻结分析选择 | ✅ |
| App A–C | Phase-I 溯源(含 09-01 无日志披露)、Phase-II 协议摘要+偏差日志指针、Phase-I 附加结果 | ✅ |

## 图

- Fig.1 `fig_phenomenon`(p4):14 harness/91 对,ρ=−0.01,图注含样本量/阶段/来源,声明 pair 非独立
- Fig.2 `fig_design`(p7):Phase-II 设计图
- 待 §5 数据完成后:主效应 + 分 builder×seed CI 图(`analysis_primary.py` 输出)

## 下一步(提示词二,采集完成后)

1. 完整性验收(18 A/D cell × 1169 + 四臂 × core-400;重复/冲突/D13 缓存语义核查)
2. 冻结分析 → 主表/图回填 §5 → 摘要/引言/讨论数字更新 → 按结果选择结论草案
3. R2/R3 审计入附录
4. Codex 独立复审(提示词三)→ 9/18 AoE 摘要提交

## 历史文档状态(不再作为执行依据)

- `PHASE2_FREEZE.md`、`PHASE2_SAP.md`、`experiment/phase2/SAP_v2.md`:tombstone,指向 `PHASE2_PROTOCOL.md`
- `PHASE2_SUMMARY.md`、`experiment/phase2/NEXT_STEPS.md`、`CURRENT_STATE.md`、`P0_BLOCKER_REPORT.md`:历史快照(含已过期预算/日期表述),仅供追溯
- 旧版 8.4/10 审稿记录:对应已被超越的旧稿,不作为当前版本放行依据
