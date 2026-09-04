# Phase-II ICLR Submission: Current Status and Decision Point

**Date:** 2026-09-04 (deadline facts corrected)
**Target:** ICLR 2027 (Abstract: Sept 18, Full paper: Sept 25)

---

## Executive Summary

The paper has a **strong core finding** (syntactic diversity ≠ behavioral diversity) but **critical methodological vulnerabilities** that will draw reviewer fire. The Codex adversarial audit identified **7 blocking issues** that must be fixed before submission.

**Current reviewer expectation:** 5/10 (Marginally below acceptance threshold)  
**With full fixes:** 6-7/10 (Weak Accept to Accept)

**The gap is fixable, but requires ~$26K API spend and 20 days of focused work.**

---

## What's Working

✅ **Core phenomenon is real and memorable:** Code diversity collapses to outcome uniformity  
✅ **T1-T3 taxonomy adds insight:** Explains WHY collapse happens (mechanisms never execute)  
✅ **Human positive control is solid:** Task does have routing space (7.3pp headroom)  
✅ **Negative routing result is valuable:** Diversity necessary but not sufficient  
✅ **Infrastructure is production-grade:** Conformance suite, official judge, trace audit  
✅ **Authors are transparent:** Acknowledge post-hoc analysis, negative results, limitations

---

## What's Broken (Blocking Issues)

🚨 **B1. Evaluation contamination** (CRITICAL)  
- Developed protocol on 24 tasks that ARE IN the confirmatory set
- Looks like post-hoc analysis dressed as preregistration
- **Fix:** New 1000+ task untouched set ($12K, 4 days)

🚨 **B2. Forced diversity is human-injected, not AI-discovered**  
- Authors hand-picked 8 mechanisms and told builder to implement them
- Not "AI restored diversity" — it's "structured specs prevent collapse"
- **Fix:** Arm E already built, needs full run ($500, 1 day) + reframe claim

🚨 **B3. Point-estimate admission with overlapping CIs**  
- "C passes at 5.96pp, A fails at 4.64pp" when CIs overlap at 5pp threshold
- Smells like p-hacking
- **Fix:** Report continuous effect sizes, eliminate binary gates (no new experiments)

🚨 **B4. "Pre-registration" is actually an audit trail**  
- Git history initialized retrospectively, no external timestamp
- **Fix:** Change wording, push public hash before evaluation (no cost)

🚨 **B5. Single-generation luck (no repeated seeds)**  
- One seed per builder — could be sampling noise
- **Fix:** 3 seeds already running, need full evaluation matrix ($1.5K incremental)

🚨 **B6. Cache-induced coupling**  
- Old cache key omitted model ID, could cause artificial collapse
- **Fix:** Already fixed, needs cache-sensitivity analysis ($800)

🚨 **B7. Collector thread-safety bug**  
- Shared harness state across threads corrupts traces
- **Fix:** Already fixed, audit whether old data is contaminated (potentially $10K rerun)

---

## What's Missing (High Priority)

📊 **H1. Single domain limits generalization**  
- BIRD-only finding, could be text-to-SQL specific
- **Fix:** SWE-bench replication ($6.5K, 7 days)

📊 **H2. Single target family limits transfer**  
- Only tested GLM-to-GLM transfer
- **Fix:** 4-target evaluation matrix ($3K, 2 days)

📊 **H3. Routing failure under-investigated**  
- One AUROC number, no analysis of WHY it failed
- **Fix:** Task/DB/harness holdout splits, LLM baseline ($2K, 3 days)

📊 **H4. Builder generalization weak**  
- Originally 3 builders, now 6 but not all may succeed
- **Fix:** Already in progress (no incremental cost)

---

## Budget Breakdown

| Fix | Cost | Days | Impact |
|-----|------|------|--------|
| **BLOCKING** | | | |
| B1: New confirmatory set | $12K | 4 | Makes study defensible |
| B5: 3-seed replication | $1.5K | 2 | Already mostly done |
| B6: Cache sensitivity | $0.8K | 1 | Quantifies confound |
| B2: Arm E full run | $0.5K | 1 | Supports reframed claim |
| B3: Continuous effects | $0 | 1 | Stats rewrite only |
| B4: Public hash | $0 | 0.5 | Wording fix |
| **HIGH PRIORITY** | | | |
| H1: Cross-domain (SWE-bench) | $6.5K | 7 | Generalization claim |
| H2: 4-target transfer | $3K | 2 | Transfer claim |
| H3: Routing deep-dive | $2K | 3 | Explains negative result |
| **TOTAL** | **~$26K** | **~20d** | **5→7 score jump** |

---

## Three Paths Forward

### Path A: Full Defense ($26K, 20 days)

**What you get:**
- Clean 1000+ task confirmatory set (untouched)
- 3 independent generation seeds (robustness)
- Cross-domain replication (generalization)
- 4-target transfer (not builder-specific)
- Deep routing analysis (explains boundary)
- Cache confound quantified
- Arm E demonstrating discovery vs injection distinction

**Expected outcome:** 6-7/10, strong Accept or weak Accept with high confidence  
**Risk:** Still might get 6 if cross-domain fails to replicate, but negative result is publishable  
**Timeline:** Tight but feasible for Sept 25 deadline

---

### Path B: Blocking Only ($15K, 10 days)

**What you get:**
- New confirmatory set
- 3-seed robustness
- Cache analysis
- Arm E
- Continuous effect sizes

**What you skip:**
- Cross-domain (acknowledge single-domain limitation)
- 4-target transfer (report GLM-only)
- Deep routing analysis (basic AUROC only)

**Expected outcome:** 6/10 weak Accept, with noted limitations  
**Risk:** Borderline — one hostile reviewer can sink it  
**Timeline:** Comfortable for Sept 25

---

### Path C: Minimal ($3K, 5 days)

**What you get:**
- Current 72-run generation evaluated on existing 151-task pilot set
- Relabel as "development study" with acknowledged contamination
- Basic stats

**What you skip:**
- Everything else

**Expected outcome:** 5/10 borderline reject  
**Risk:** High rejection probability  
**Timeline:** Fast, but result is weak

---

## Recommendation

**Go with Path A (full defense) IF:**
- You want a strong ICLR publication
- $26K is within budget
- You can commit to focused 20-day sprint

**Go with Path B (blocking only) IF:**
- Budget is constrained but you can afford $15K
- Willing to accept "solid but limited" rather than "strong"
- Want safer timeline

**Go with Path C (minimal) IF:**
- Budget is very tight
- Willing to risk rejection for a workshop/second-tier venue
- Want to get something submitted quickly

---

## Current Status (as of 2026-09-04, end of day; written 2026-09-04)

✅ Generation: 24/72 runs complete (seed 0 done), 48 more in progress  
✅ Evaluation infrastructure: Complete, tested, committed  
✅ Blocking issues: Identified, fixes documented  
✅ Corrected protocol: SAP v2.0 written  
✅ Cross-domain plan: Scoped and costed  
⏸️ **WAITING FOR USER DECISION:** Which path to take?

---

## Critical Next Steps (once user decides)

### Tomorrow (Sept 6):
1. Check generation completion (should be 72/72)
2. Audit yield table (target: 18 paired cells)
3. Freeze protocol v2.0 (commit + SHA256 hash)
4. **GET USER BUDGET APPROVAL**

### If Path A approved:
5. Generate new 1000-task split from untouched databases
6. Run cache sensitivity analysis
7. Kick off confirmatory evaluation matrix

### If Path B approved:
5. Generate new 1000-task split (smaller, ~600 tasks to save cost)
6. Skip cross-domain and 4-target
7. Run confirmatory on reduced scope

### If Path C approved:
5. Evaluate current generation on existing 151 pilot
6. Write paper with heavy limitations section
7. Submit and hope

---

## Open Questions (need user answers)

1. **Which path?** A ($26K, strong), B ($15K, safe), or C ($3K, risky)?
2. **ICLR 2027 confirmed?** Abstract Sept 18, full paper Sept 25?
3. **Author list finalized?** Cannot change after abstract submission
4. **Risk tolerance?** Aim for 7 or settle for 6?
5. **What happens if generation fails?** (Currently at 24/72, might not reach 18 paired cells)

**User input needed before proceeding with confirmatory evaluation.**

---

## Contact

- Detailed vulnerability analysis: `experiment/phase2/REVIEWER_ATTACKS.md`
- Updated protocol: `experiment/phase2/SAP_v2.md`
- Cross-domain plan: `experiment/phase2/CROSS_DOMAIN_PLAN.md`
- Execution checklist: `experiment/phase2/NEXT_STEPS.md`

**Everything is ready to execute once the user picks a path.**
