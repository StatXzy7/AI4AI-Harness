# Abstract + §7 Discussion + §8 Conclusion

*(draft v2, 2026-09-03 — eval151 判定后定稿:正文采用下方 Abstract 定稿版;原 Draft A/B 草稿留档备查。)*

## Abstract (定稿)

Large language models are increasingly wrapped in **harnesses** — generated programs of
prompts, tools, and control flow — and a growing literature routes over *populations*
of such harnesses per query. Routing presupposes that population members disagree
behaviorally. We show this presupposition fails for automatically generated
populations: on BIRD text-to-SQL with a frozen mid-tier target, the candidates of a
standard harness-evolution loop are syntactically diverse (mean pairwise code
similarity 0.14) yet behaviorally collapsed (96% outcome agreement; 21 of 66 candidate
pairs identical on every task; the shipped ReAct variant reproduces bare's final SQL
byte-for-byte on every audited task). Execution-trace auditing resolves the collapse
into three failure classes: mechanisms described but absent from the control flow,
feedback with no causal path to the output, and broken multi-turn paths. A hand-written
positive control on the same target, tasks, and judge delivers 7.3 pp oracle headroom
on 151 held-out questions — the headroom routers need is real, and it is the
*generation* side that fails. We then show the gap is a protocol property, not a
capability ceiling: under a mechanism-gated free-form protocol, two of three builders
produce populations that exceed pre-registered diversity thresholds at the point
estimate for the first time (6.0 and 8.0 pp headroom; six pairwise-distinct repair
sets each), while the old un-gated protocol misses and the weakest builder produces
no accepted candidate — both axes are implicated, though the design cannot separate
their main effects. Diversity, however, is necessary, not sufficient: a
leave-one-harness-out value predictor over the admitted populations does not beat the
best fixed harness (≤0.001 AUROC over task-only features), its apparent per-task
signal is task memorization and vanishes on task-level held-out splits, and its one
deployment-relevant success — +6.9 pp over bare with zero induced harm — holds only
as an abstaining gate over the full 24-harness pool. We release a three-metric
precondition checklist — pairwise disagreement, union repair, oracle headroom — that
harness-generation and harness-routing papers can and should report before routing is
attempted.

## §7 Discussion

**The checklist as a community tool.** The three metrics of §4 are computable from the
outcome matrix any evaluation already produces. A routing paper whose population fails
the checklist has, at best, rediscovered its best fixed harness; we argue the checklist
should be reported alongside accuracy, the way calibration plots accompany
confidence-based methods.

**Implications for AI4AI generation.** T1–T3 imply concrete protocol requirements:
(i) acceptance must be defined on *traces*, not docstrings or code diffs; (ii) feedback
mechanisms need a demonstrated causal path (the modified answer must depend on the
executed artifact); (iii) executable-output validation precedes any capability claim.
The IR arm shows the third requirement is not enough on its own: compiled mechanism
diversity yielded the most distinct fix sets (6/6) yet only 3.97 pp headroom —
mechanisms must also be *selected against a headroom landscape*, which is exactly the
information the checklist surfaces.

**Why stronger builders are not automatically the fix.** Under the gated protocol, the
builder axis orders generation reliability and population quality (GLM 0/6 accepted;
Qwen 5.96 pp; DeepSeek 7.95 pp). But the old protocol's failure mode is different in
kind: its best member (0.583, the strongest harness in the study) *dominates*, so the
population's remaining headroom falls to 4.64 pp even with a healthy repair rate —
missing the threshold by 0.36 pp rather than collapsing. A strong builder without a
behavioral gate concentrates quality; a gate without a capable builder produces
nothing. The two axes are complements by these contrasts, and the checklist detects
which one is binding — while we acknowledge the design cannot separate main effects.

**Limitations.** One domain family (text-to-SQL; a second database for build–eval
disjointness), one frozen target, K=6 populations, and execution-accuracy judging
(set-of-rows equality, not BIRD's official scorer). 24 of the 151 evaluation items
overlap with earlier protocol-development runs — this overlap is disclosed, and the
A-arm population selection used only the 36 fully disjoint items. The human control
was designed after inspecting day-1 traces, so its headroom is an existence proof,
not a blind estimate. Pre-registered thresholds were set from 60-item evidence; the
borderline populations (IR at 3.97 pp, human control at 14.9% repair) are reported
exactly as measured, without post-hoc adjustment. Bootstrap intervals on 151 items
are wide — roughly ±9–11 pp on repair rates — and all raw metrics are released so
stricter readings can be applied. Finally, the admission decision follows the frozen
point-estimate rule; readers applying interval-based standards would admit fewer
populations, and we say so where it matters.

## §8 Conclusion

AI-generated harness populations can be exactly what their source files suggest and
nothing like what routing needs. We measured that gap — mean code similarity 0.14
against 96% behavioral agreement — explained its mechanism at the trace level, showed
the missing headroom is recoverable by hand (7.3 pp), and then showed it is also
reachable automatically: mechanism-gated generation with capable builders restores
behavioral diversity (two admitted populations, up to 8.0 pp headroom at the point
estimate) where the old protocol misses the pre-registered headroom threshold. What
diversity does not yet buy is open-set routing — unseen-harness value prediction
remains unsolved, under both harness-level and task-level generalization — so the
practical output of this paper is deliberately small and reusable: report
disagreement, union repair, and headroom before you route; gate generation on traces,
not text.

## 备档:原 Draft A/B abstract 草稿要点

- Draft B(负结果主分支)与 Draft A(达标主分支)原文见 git 历史或 2026-09-02 版;
  判定后实际落点为"A 版多样性别修复 + F4 边界结果"的混合,即上方定稿版。
