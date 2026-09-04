# P0 BLOCKER REPORT — Phase-II State Correction

**Date:** 2026-09-04
**Auditor:** Codex adversarial review  
**Executor:** ZCode (this agent)

---

## CRITICAL: API Key Exposure (P0-BLOCKER-1)

**Status:** CONFIRMED EXPOSED

**Location:**
- `experiment/phase2/parallel_gen.sh:3`
- `experiment/phase2/sweep_seeds12.sh:3`

**Exposed credential:** `[REDACTED-ROTATE-ON-PROVIDER]` (Paratera API key)

**Git history status:** Checking...

```bash
git log --all --full-history --source --oneline -- \
  experiment/phase2/parallel_gen.sh \
  experiment/phase2/sweep_seeds12.sh | head -20
```

**Immediate actions required:**

1. **USER MUST:** Revoke `[REDACTED-ROTATE-ON-PROVIDER]` at Paratera immediately
2. **USER MUST:** Generate new API key, store in environment variable only
3. **ZCode WILL:** Rewrite scripts to use `${PARATERA_API_KEY}` instead of hardcoded value
4. **USER MUST DECIDE:** Whether to scrub git history (breaks remote refs) or accept leaked key in history

**Risk if not fixed:**
- Exposed API key can be used for unauthorized LLM access
- Cost abuse / quota exhaustion
- Attribution contamination (external actors using your key)
- Cannot publish code repository in current state

---

## P0-BLOCKER-2: Phase-II Generation Output Path Mismatch

**Status:** CONFIRMED — seed 1 outputs written to wrong location

**Expected location:** `E:\projects\AI4AI-Harness\artifacts\phase2\gen\`  
**Actual location:** `E:\artifacts\phase2\gen\` (outside repo)

**Impact:**
- Repository monitoring shows 24/72 (seed 0 only)
- Seed 1 outputs (20 logs) exist but are invisible to version control
- Seed 2 not yet started
- Cannot claim "72 runs complete" when only 24 are tracked

**Root cause:** Relative path resolution in `parallel_gen.sh` and `sweep_seeds12.sh`

---

## P0-BLOCKER-3: Evidence-Claim Misalignment in Current Draft

**Status:** CONFIRMED — paper claims not supported by frozen protocol

**Specific issues:**

1. **"Old protocol collapses on all builders"** — FALSE
   - Paper: [sec_protocols.tex:132] states old protocol collapsed across builders
   - Reality: Qwen/DeepSeek 40 candidates are byte-identical `bare.py` copies
   - Verdict: 780/780 identical outcomes is tautology (same code → same result), NOT behavioral collapse
   - Source: [PHASE2_FREEZE.md:178]

2. **"151-task evaluation is confirmatory"** — FALSE
   - Paper uses "held-out", "pre-specified", "load-bearing" throughout
   - Reality: 24/151 tasks participated in protocol development, human control designed post-diagnosis
   - Verdict: Phase-I is discovery/pilot by frozen protocol definition
   - Source: [PHASE2_FREEZE.md:5]

3. **"Pre-registered thresholds"** — OVERCLAIMED
   - Paper implies external preregistration
   - Reality: Internal audit trail, retrospectively initialized git, no external timestamp
   - Verdict: "Pre-evaluation frozen internal protocol" at most, not formal preregistration

**Actions required:**
- Rewrite Abstract, Introduction, §6.4, Discussion, Conclusion
- Relabel Phase-I as "Discovery Study"
- Remove all "confirmatory" language from 151-task results
- Phase-II (when complete) will be the confirmatory study

---

## P0-BLOCKER-4: ICLR 2027 Submission Non-Compliance

**Status:** CONFIRMED — current draft cannot be submitted as-is

**Issues:**

1. **Wrong template:** Using `iclr2026_conference.sty` instead of ICLR 2027 template
2. **Missing AI-use disclosure:** ICLR 2027 mandatory policy requirement not present
3. **Final-copy mode enabled:** `\iclrfinalcopy` should be OFF for submission
4. **Incomplete references:** 15+ citations with "TTHE authors", "ID to be re-verified", "Complete ID to be resolved"

**Source:** [main.tex:2], [references.bib:3], ICLR 2027 Author Guidelines

**Actions required:**
- Download ICLR 2027 template
- Add AI-use disclosure statement
- Disable `\iclrfinalcopy`
- Complete all reference entries before submission

---

## P1 HIGH-PRIORITY (not blocking, but affects credibility)

### P1-1: No figures in 12-page draft
- PAPER_PLAN.md specified 4 figures
- Current PDF has zero figures
- Dense text + long tables = high reviewer cognitive load

### P1-2: Bibliography in placeholder state
- Cannot support "first systematic measurement" claims with incomplete citations
- Risk: Concurrent work may have priority, cannot verify without complete survey

### P1-3: Editorial errors
- Duplicate Discussion/Conclusion headers
- "two nested contrasts, originally two nested contrasts" repetition in appendix
- Line 65 of sec_appendix.tex

### P1-4: Date errors in planning documents
- PHASE2_SUMMARY.md shows Sept 19 abstract deadline (actual: Sept 18)
- Multiple documents use future dates for past events

---

## Current Generation Status (Actual)

**Repository-tracked (artifacts/phase2/gen/):**
- Seed 0: 24 logs (6 builders × 4 arms)

**Outside repository (E:\artifacts\phase2\gen/):**
- Seed 1: 20 logs (partial, some builders/arms incomplete)

**Not started:**
- Seed 2: 0 logs

**TRUE STATUS: 24-44 / 72 runs complete (33-61%), NOT 72/72**

---

## What ZCode Will Do Now (Zero-Cost Fixes)

1. ✅ Remove hardcoded API keys from scripts
2. ✅ Fix output paths to write to repository
3. ✅ Audit E:\artifacts\phase2 for seed 1 results
4. ✅ Generate SHA-256 manifest of all Phase-II outputs
5. ✅ Create unified Phase-II protocol from 3 conflicting versions
6. ✅ Write CURRENT_STATE.md with true completion matrix
7. ✅ Commit freeze marker BEFORE looking at any confirmatory results

**NOT doing yet:**
- Rewriting paper (wait for Phase-II results)
- Starting cross-domain experiments
- Claiming experiments are complete
- Looking at split_p2_test outcomes

---

## What USER Must Do

1. **IMMEDIATE:** Revoke Paratera API key `sk-8YAa...31OA`
2. **IMMEDIATE:** Generate new key, set as environment variable
3. **DECIDE:** Scrub git history or accept leaked key in repo history
4. **DECIDE:** Path A ($26K), Path B ($15K), or Path C ($3K) — see PHASE2_SUMMARY.md
5. **DECIDE:** Run remaining 28-48 generation jobs with new key?

---

## State After This Fix

- API keys removed from tracked scripts
- Generation outputs consolidated and manifested
- True completion status documented
- Protocol frozen with real commit SHA
- Paper NOT yet updated (waiting for Phase-II results)
- Confirmatory outcomes NOT yet examined

**This establishes a clean baseline for Phase-II confirmatory evaluation.**

