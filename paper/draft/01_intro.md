# §1 Introduction

*(draft v2, 2026-09-03 — eval151 判定后回填完毕。数字溯源:§6.0 表 + DAY2_RESULTS.md。)*

The fastest-growing lever on a frozen LLM is no longer weights but the *harness* — the
program of prompts, tools, and control flow that wraps the model for a task. A recent
wave of systems generates this scaffolding automatically: LLM builders propose, edit,
and evolve harness code, with reported gains over bare prompting. The implicit premise
of this "AI4AI" line is that when the generated code differs, the *behavior* differs —
that a population of thirty harnesses is thirty ways of answering, not one way written
thirty times.

We test that premise directly. On BIRD text-to-SQL with a frozen mid-tier target, we
take the full candidate population produced by a standard harness-evolution loop and
measure what its members actually do, not what their source files say. The population
is a lesion: every candidate passes a code-difference check, yet among the 12
generated candidates average pairwise outcome disagreement is **3.8%** and **21 of 66
candidate pairs are behaviorally identical** (28 of 78 pairs once the shipped ReAct
harness is included); the ReAct variant reproduces the bare baseline's final SQL
**byte-for-byte on every audited task**. Execution traces explain the gap with a
three-class taxonomy — mechanisms *described* but absent from the control flow, feedback
with no causal path to the output, and genuinely multi-turn paths that are broken. We
call this **behavioral collapse**: syntactic diversity without behavioral diversity
(F1).

Collapse is not a property of the task. Four hand-written harnesses with forcibly
distinct execution paths — execute-and-repair, three-way voting, schema-linking,
hint-first — run on the same frozen target and deliver a **6.7 pp oracle headroom**
over the best fixed harness on 60 tasks (7.3 pp on 151), with three of the four
producing repairs the others miss (F2). The headroom that harness routers and value
predictors need is real; it is the generation side that fails to populate it.

If the bottleneck is generation, the obvious next question is whether it is a
*capability* bottleneck (a stronger builder would fix it) or a *protocol* bottleneck
(no builder is asked, checked, or forced to change behavior). We probe both axes with
two nested contrasts (not a full factorial; §3.4): a pre-specified builder sweep
under a **strategy-forced free-form** protocol — which assigns each candidate an
explicit control-flow mechanism and accepts the emitted artifact only after an
import and execution smoke check — run with GLM, Qwen, and DeepSeek; and a **Harness IR** that compiles declarative mechanism
specifications into harness code deterministically, guaranteeing mechanism diversity
by construction and isolating "what mechanisms do" from "whether the builder can
write code". On the builder-held-out 151-question set, both stronger-builder gated
populations exceed all three pre-specified diversity thresholds at the point
at the point estimate — 5.96 and 7.95 pp oracle headroom, six pairwise-distinct
repair sets each — while the old proposer protocol misses the headroom threshold
(4.64 pp, its best member dominating); and on completed strategy grids every
builder's population clears the checklist (up to 9.93 pp for DeepSeek, and even the
GLM builder's three accepted harnesses reach 5.96 pp), with per-strategy generation
acceptance ordering by builder (GLM 3/8, Qwen 7/8, DeepSeek 8/8, fully logged):
both axes are implicated, though the design cannot separate their main effects; a
K-controlled subsampling analysis shows the gap is not a population-size effect
(the old protocol never crosses the 5 pp line at any K, while strategy-forced
populations exceed it at K=2) (F3).
A leave-one-harness-out value predictor over these admitted populations, however, does
not beat the best fixed harness — and its apparent per-task signal is task
memorization: in a task-held-out control on D6 it falls to chance (AUROC 0.475).
Behavioral diversity is
*necessary* for routing value to exist, but estimating an unseen harness's value from
code and task text alone remains open (F4).

Our contributions:

1. **The first systematic outcome-matrix measurement of behavioral collapse** in
   AI-generated harness populations — narrow the priority claim as: the first
   measurement, on a full generated population's outcome matrix, of the gap between
   syntactic diversity and behavioral diversity, with an execution-trace taxonomy
   explaining *why* code diversity fails to become behavioral diversity. Concurrent
   work uses behavior-aware verification inside evolution systems (§2); none measures
   population-level collapse as an outcome phenomenon.
2. **A controlled generation-side study**: two nested contrasts — a builder sweep
   (GLM / Qwen / DeepSeek) under the strategy-forced protocol plus an old-protocol arm
   and a compiled IR arm with a human positive control — evaluated under pre-specified
   admission thresholds on the builder-held-out 151-question set, showing behavioral
   diversity is restorable (two admitted populations), that the old protocol's
   failure mode is quality concentration rather than absence of repairs, and that
   per-strategy generation acceptance orders with builder capability (3/8 vs 7/8
   vs 8/8, logged).
3. **A boundary result for the routing literature**: on the admitted populations,
   open-set harness-value prediction fails to beat the best fixed harness
   (≤0.001 AUROC over task-only features), and in a task-held-out control its repair
   signal falls to chance — while the same
   predictor used as an abstaining gate over the 24-harness pool gains +6.9 pp over
   bare with zero induced harm there. Diversity is necessary, not sufficient, and the
   precondition checklist tells you which regime you are in.

Beyond harnesses, the failure pattern we isolate — LLM builders producing plausible,
well-documented, behaviorally inert variants — is a generation-reliability phenomenon
likely to recur wherever a model is asked to modify its own program.

<!-- 写作纪律:
  - 全部占位符已回填(2026-09-03)。若后续Exp C(ds1000 跨域)结果并入,仅动 §6/§7。
  - 数字溯源:3.5%/28/78/react D=0 → population_diagnosis.json;20.7%/6.67pp →
    positive_control_diagnosis.json(60 题);151 题判定与 CI → artifacts/day2/DAY2_RESULTS.md。 -->
