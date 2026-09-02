# §2 Related Work

*(draft v1, 2026-09-02; anchors verified 2026-08-31 in PROBLEM_FREEZE.md §1; re-verify IDs at camera-ready.
Task-CoEvolve 2608.20169 added per 2026-09-02 collision watch.)*

## 2.1 Harness generation for LLMs

A growing line of work generates task-specific scaffolding — prompts, tools, control
flow — around a frozen model. TTHE evolves text-to-SQL harnesses with an
LLM proposer/judge loop (2607.08124); a-evolve and related evolutionary systems
maintain and edit agent code populations; Self-Harness (2606.09498) shows a model can
improve its own harness; JIT-Agent (2608.25593) trains a model to *generate* a harness
per task at inference time. Task-CoEvolve (2608.20169) co-evolves tasks and scaffolds.
A concurrent 2026 cluster makes harness evolution *behavior-aware* from the
verification side: HarnessLens (2608.27311) allocates a rollout budget across task
space and behavior-level checks during evolution; HarnessFix repairs harnesses from
trace-grounded diagnoses; AHE verifies each proposed edit against self-declared
behavioral predictions; gated semantic quality-diversity search (2607.13683) evolves
populations over LLM-assigned pathology descriptors; Harness Handbook (2607.13285)
and Meta-Harness attack behavior localization and outer-loop search. These systems
treat behavior as a *signal inside the loop*; none measures whether a generated
population is behaviorally diverse as an outcome property, which is precisely the
failure we quantify: evolved candidates that pass every per-edit check can still
share one execution path with the bare baseline. Our strategy-forced free-form and
harness-IR protocols are generation-protocol fixes; they are orthogonal to, and
composable with, the search loops above.

## 2.2 Harness conditional utility and routing

Several recent papers establish that harness quality is conditional. "No Universally
Superior Harness" (2607.18235) and the non-monotonicity analysis of harness
sensitivity (2605.26731) document that no single harness dominates across instances —
the phenomenon layer. HELIX (2608.13951) shows a portfolio of sibling harnesses beats
the best fixed one by a large coverage margin and lists a harness *router* as future
work; STS (2604.06753) routes over six fixed human-designed scaffolds in a closed set;
GRASP (2605.29668) gates skill edits into a library at development time; CF search
routing (2607.05752) learns counterfactual, instance-level routing over
{no-search, search, abstain}; agentic routing (2607.11399) routes *models* within a
harness. What all of these consume — and none of them measure — is a population whose
members actually disagree. We supply the missing precondition analysis, show it fails
for naively generated populations, and give generation protocols that restore it.

## 2.3 Behavioral diversity in LLM populations

Diversity of LLM outputs has mostly been studied at the sample level
(self-consistency, diverse decoding) or the agent-policy level. The observation that
*syntactically distinct programs exhibit identical behavior* echoes coverage gaps
documented in program synthesis and in mutation-testing practice; our contribution is
to instantiate it for AI-generated harness populations — measuring, on a full
generated population's outcome matrix, the gap between syntactic and behavioral
diversity. To our knowledge (literature scan 2026-09-02, to be re-run at
camera-ready), no prior work measures this collapse as an outcome property of a
generated population; behavior-aware verification *inside* evolution systems is
concurrent independent work (§2.1).

## 2.4 Positioning summary

| System | Decides | Set of harnesses | Our difference |
|---|---|---|---|
| STS | per-query scaffold | closed, 6 human designs | open populations; we measure population viability first |
| GRASP | skill edit admission | development-time | we ask whether runtime populations are worth routing at all |
| HELIX router | (roadmap) | fixed portfolio | we provide the precondition its router needs |
| JIT-Agent | generate per task | generated on the fly | we study population diversity of frozen harnesses |
| TTHE | evolve one winner | candidates discarded | we keep and audit the whole population |
| HarnessLens / HarnessFix / AHE | in-loop verification & repair | evolving single lineage | we audit the population as an outcome, post hoc |
| Gated QD search (2607.13683) | QD exploration w/ gates | evolving population | we measure collapse + protocol effect on a fixed population |

<!-- 待办: 2607.18235/2605.26731 两篇 phenomenology 论文未在本机核实全名;
     camera-ready 前用 citation-audit 跑一遍。 -->
