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
is a lesion: every candidate passes a code-difference check, yet average pairwise
outcome disagreement is **3.5%**, **28 of 78 harness pairs are behaviorally identical**,
and the shipped ReAct-style feedback harness reproduces the bare baseline's final SQL
**byte-for-byte on every audited task**. Execution traces explain the gap with a
three-class taxonomy — mechanisms *described* but absent from the control flow, feedback
with no causal path to the output, and genuinely multi-turn paths that are broken. We
call this **behavioral collapse**: syntactic diversity without behavioral diversity
(F1).

Collapse is not a property of the task. Four hand-written harnesses with forcibly
distinct execution paths — execute-and-repair, three-way voting, schema-linking,
hint-first — run on the same frozen target and deliver **20.7% union repair** over bare
errors with **6.7 pp oracle headroom**, with three strategies contributing *unique*
repairs the others miss (F2). The headroom that harness routers and value predictors
need is real; it is the generation side that fails to populate it.

If the bottleneck is generation, the obvious next question is whether it is a
*capability* bottleneck (a stronger builder would fix it) or a *protocol* bottleneck
(no builder is asked, checked, or forced to change behavior). We disentangle the two
with a pre-registered, three-builder experiment (GLM / Qwen / DeepSeek) × two
behavior-aware generation protocols: a **gated free-form** protocol that rejects any
candidate whose execution path does not differ from bare, and a **Harness IR** that
compiles declarative mechanism specifications into harness code deterministically —
guaranteeing mechanism diversity by construction and isolating "what mechanisms do"
from "whether the builder can write code". On 151 held-out questions, both
stronger-builder gated populations clear all three pre-registered diversity thresholds
for the first time — 5.96 and 7.95 pp oracle headroom, six pairwise-distinct repair
sets each — while the old proposer protocol misses (4.64 pp) and the weakest builder
fails at generation itself (0/6): capability and protocol are jointly necessary (F3).
A leave-one-harness-out value predictor over these admitted populations, however, does
not beat the best fixed harness: behavioral diversity is *necessary* for routing value
to exist, but estimating an unseen harness's value from code and task text alone
remains open (F4).

Our contributions:

1. **The first systematic measurement of behavioral collapse** in AI-generated harness
   populations, with an outcome-level precondition checklist (pairwise disagreement,
   union repair, oracle headroom) and an execution-trace taxonomy that explains
   *why* code diversity fails to become behavioral diversity.
2. **A controlled generation-side study**: three builders × two behavior-aware
   protocols plus a compiled IR arm and a human positive control, evaluated under
   pre-registered admission thresholds on 151 held-out questions.
3. **A boundary result for the routing literature**: on the admitted populations,
   open-set harness-value prediction still fails to beat the best fixed harness
   (≤0.001 AUROC over task-only features), while the same predictor used as an
   abstaining gate gains +6.9 pp over bare with zero induced harm — diversity is
   necessary, not sufficient, and the precondition checklist tells you which regime
   you are in.

Beyond harnesses, the failure pattern we isolate — LLM builders producing plausible,
well-documented, behaviorally inert variants — is a generation-reliability phenomenon
likely to recur wherever a model is asked to modify its own program.

<!-- 写作纪律:
  - 全部占位符已回填(2026-09-03)。若后续Exp C(ds1000 跨域)结果并入,仅动 §6/§7。
  - 数字溯源:3.5%/28/78/react D=0 → population_diagnosis.json;20.7%/6.67pp →
    positive_control_diagnosis.json(60 题);151 题判定与 CI → artifacts/day2/DAY2_RESULTS.md。 -->
