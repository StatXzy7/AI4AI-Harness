# Phase-II Cross-Domain Replication Plan

## Objective

Replicate the core collapse → forced-diversity findings on a second domain to demonstrate
the phenomenon is not BIRD-specific. Does NOT require the full factorial — only enough to
answer: "Does outcome collapse appear elsewhere, and can explicit strategy forcing prevent it?"

## Domain: SWE-bench Verified

**Why SWE-bench Verified:**
- 500 human-validated real-world GitHub issues
- Execution-based correctness (passes repo tests)
- Public, contamination-auditable
- Stronger external validity than synthetic coding benchmarks

**Fallback:** LiveCodeBench if SWE-bench infrastructure proves brittle.

---

## Minimal Replication Design

### Phase 1: Collapse Discovery (OLD protocol equivalent)

**Builder:** DeepSeek-V4-Pro (strongest from BIRD)  
**Target:** Claude Opus 5 (frontier code model)  
**Protocol:** Free-form generation, neutral validity gate only  
**K:** 8 harnesses  
**Seeds:** 1 (not 3 — this is a replication probe, not the primary study)  

**Evaluation split:** 200 random SWE-bench Verified tasks (40% of corpus)

**Metrics:**
- Pairwise disagreement
- Union repair over bare Opus baseline
- Oracle headroom
- K_eff (unique outcome vectors)

**Expected result if collapse replicates:** disagreement < 10%, headroom < 3pp, K_eff < 0.5

---

### Phase 2: Forced Diversity (STRATEGY-FORCED protocol)

**Same builder/target/split**

**Strategies (6 mechanisms, not 8):**
1. **test_first** — run existing repo tests, parse failures, regenerate fix
2. **lint_repair** — run linter/type-checker, feed errors back
3. **vote3** — generate 3 independent patches, vote by test pass rate
4. **decompose** — break issue into sub-tasks, solve sequentially
5. **two_view** — minimal patch vs full-context rewrite, pick by tests
6. **search_codebase** — grep for similar patterns before generating

**Gate:** Conformance suite adapted for code domain (execution steps, error propagation,
candidate sampling — same DSL, different instrumentation)

**Metrics:** same as Phase 1

**Expected result if forcing works:** disagreement > 15%, headroom > 5pp, K_eff > 0.7

---

### Phase 3: Human Positive Control

**Hand-written implementations** of the 6 strategies above, executed on the same 200 tasks.

**Purpose:** Establish that the task distribution genuinely supports conditional routing,
so negative results in Phase 2 cannot be dismissed as "SWE-bench has no routing space."

**Expected:** headroom 8–15pp (real issues have high conditional complexity)

---

## Resource Budget

### API Costs (estimated)

**Phase 1 (collapse):**
- 8 harness generations: ~$50 (DeepSeek)
- 200 tasks × 8 harnesses × Opus: ~$800

**Phase 2 (forced):**
- 6 × 8 = 48 generations: ~$300
- 200 tasks × 48 harnesses × Opus: ~$4,800

**Phase 3 (control):**
- 200 tasks × 6 hand-written × Opus: ~$600

**Total:** ~$6,550

**Mitigation:** Run Phase 1 first; only proceed to Phase 2 if collapse replicates.

---

## Timeline

**Sept 5–6:** Adapt harness scaffold to SWE-bench (patch generation, test execution, git ops)  
**Sept 7:** Phase 1 generation + evaluation  
**Sept 8:** If collapse confirmed, run Phase 2  
**Sept 9–10:** Human control + analysis  
**Sept 11:** Cross-domain table ready for paper

---

## Implementation Checklist

- [ ] SWE-bench Verified dataset download + 200-task split
- [ ] Harness base class adapted for code domain
- [ ] Test executor (docker-based, matches official SWE-bench judge)
- [ ] Conformance suite for code (adapted probes)
- [ ] 6 strategy prompts
- [ ] Collection pipeline
- [ ] Dual-judge re-scoring (SWE-bench official evaluator)
- [ ] Cross-domain table generator

---

## Acceptance Criteria for Paper

**Minimum to include cross-domain section:**
- Phase 1 shows collapse (disagreement < 12%)
- Phase 2 shows forcing helps (headroom delta > 0)
- Human control establishes task feasibility

**If this holds:** Section 6 "Cross-Domain Replication" reports both domains side-by-side,
strengthening the claim that collapse is a general AI4AI phenomenon.

**If Phase 2 fails:** Still publish as boundary result — "forcing worked on SQL but not code,
suggesting mechanism transferability is limited" — which is a valid finding.
