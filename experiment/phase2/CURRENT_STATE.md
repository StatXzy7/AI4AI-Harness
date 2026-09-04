# Phase-II Current State — Post-Correction

**Date:** 2026-09-05 (actual audit date)  
**Last Updated:** After P0 fixes  
**Status:** Clean baseline established, awaiting user decision

---

## P0 Blockers — Status

### ✅ FIXED: API Key Exposure
- **Action taken:** Removed hardcoded `sk-8YAaA4ry1ToVzXRdq331OA` from scripts
- **New behavior:** Both scripts now require `$PARATERA_API_KEY` environment variable
- **Backups:** `.backup` files preserved
- **Git history:** Key appears in 1 commit (`6f64f36`), pushed to main
- **USER ACTION REQUIRED:** 
  - Revoke exposed key at Paratera immediately
  - Generate new key, set as environment variable
  - Decide: scrub git history or accept exposure

### ✅ FIXED: Output Path Mismatch
- **Problem:** Seed 1 wrote to `E:\artifacts\phase2\gen` (outside repo)
- **Action taken:** 24 seed 1 files copied to `artifacts/phase2/gen/`
- **Verification:** SHA-256 manifest in `experiment/phase2/seed1_external_manifest.txt`
- **Scripts updated:** `sweep_seeds12.sh` now uses absolute repo paths

### ⏸️ PENDING: Evidence-Claim Misalignment
- **Status:** Documented in P0_BLOCKER_REPORT.md
- **Action:** Will be fixed during paper rewrite AFTER Phase-II results
- **Not touching paper yet:** Waiting for confirmatory outcomes

### ⏸️ PENDING: ICLR 2027 Compliance
- **Status:** Documented in P0_BLOCKER_REPORT.md
- **Action:** Template/AI-use disclosure will be added before submission
- **Not blocking experiments:** Can proceed with generation/evaluation

---

## Generation Status (TRUE as of now)

### Repository Inventory

| Seed | A | B | C | D | Total | Expected |
|------|---|---|---|---|-------|----------|
| 0    | 6 | 6 | 6 | 7 | 25    | 24       |
| 1    | 6 | 6 | 6 | 6 | 24    | 24       |
| 2    | 0 | 0 | 0 | 0 | 0     | 24       |
| **TOTAL** | **12** | **12** | **12** | **13** | **49** | **72** |

**Note:** Seed 0 has 25 files instead of 24 — investigating duplicate/extra file.

### Paired Cells (A + D both present)

Required for primary D−A contrast: **18 cells** (6 builders × 3 seeds)

**Current: 12 / 18 (67%) ✓**

| Builder  | Seed 0 | Seed 1 | Seed 2 | Status |
|----------|--------|--------|--------|--------|
| glm      | ✓      | ✓      | ✗      | 2/3    |
| qwen     | ✓      | ✓      | ✗      | 2/3    |
| deepseek | ✓      | ✓      | ✗      | 2/3    |
| kimi     | ✓      | ✓      | ✗      | 2/3    |
| minimax  | ✓      | ✓      | ✗      | 2/3    |
| ernie    | ✓      | ✓      | ✗      | 2/3    |

**All 6 builders successful on seeds 0-1 ✓**

**Remaining:** Seed 2 sweep (24 runs) needed to reach 18 paired cells

---

## Protocol Status

### Three Conflicting Documents

1. `PHASE2_FREEZE.md` — v1.0 original freeze (contamination acknowledged)
2. `PHASE2_SAP.md` — v1.0 statistical plan
3. `experiment/phase2/SAP_v2.md` — v2.0 with Codex fixes (still says "TBD")

**Action needed:** Merge into single authoritative protocol

### Key Protocol Rules (Codex-corrected)

✅ Equal raw generation budget (R=3 per slot)  
✅ Slot failure is final (no backfill)  
✅ Bare-inclusive oracle headroom as primary metric  
✅ Primary contrast: D−A paired by (builder, seed)  
✅ Report CONTINUOUS effect sizes (not binary pass/fail)  
✅ Cache isolated per (run_id, model, config)  
✅ Collector uses per-task harness instantiation  
✅ Official BIRD judge with 30s timeout  
✅ Conformance gate uses counterfactual probes  

🔴 **NOT YET DONE:** Frozen commit with SHA-256 hash  
🔴 **NOT YET DONE:** Public timestamp before looking at outcomes

---

## What Has NOT Been Examined Yet

**Zero confirmatory outcomes viewed:**
- No `split_p2_test` results loaded
- No primary D−A contrast computed
- No builder/target/routing analysis performed
- No figures generated

**This state must be preserved until:**
1. User approves budget path (A/B/C)
2. Protocol is frozen with commit SHA
3. Hash is pushed publicly

---

## Cost Estimates (from PHASE2_SUMMARY.md)

### Path A: Full Defense ($26K)
- New 1000+ task confirmatory set
- 3-seed replication (mostly done)
- Cross-domain (SWE-bench)
- 4-target transfer
- Routing deep-dive
- **Expected:** 6-7/10

### Path B: Blocking Only ($15K)
- New confirmatory set (smaller)
- 3-seed replication
- Cache analysis
- Arm E evaluation
- **Expected:** 6/10

### Path C: Minimal ($3K)
- Use current 151-task pilot
- Acknowledge contamination
- **Expected:** 5/10 borderline reject

---

## Immediate Next Actions

### User Must Decide

1. **Revoke exposed API key** (URGENT)
2. **Choose path:** A ($26K), B ($15K), or C ($3K)
3. **Approve seed 2 generation?** (need new API key)
4. **Git history:** Scrub or accept exposure?

### ZCode Will Do Next

**If seed 2 approved:**
1. Wait for new `$PARATERA_API_KEY` from user
2. Run: `bash experiment/phase2/sweep_seeds12.sh` (but only seed 2)
3. Verify 18 paired cells complete

**Once generation complete:**
4. Merge protocol documents into single authoritative version
5. Generate protocol freeze commit with SHA-256
6. Push hash publicly (tweet/gist) BEFORE looking at outcomes
7. Then and only then: run confirmatory evaluation

**NOT doing:**
- Looking at split_p2_test outcomes
- Rewriting paper
- Starting cross-domain
- Making any claims about "experiments complete"

---

## Files Created/Modified This Session

### Created
- `experiment/phase2/P0_BLOCKER_REPORT.md` — Detailed P0 analysis
- `experiment/phase2/seed1_external_manifest.txt` — SHA-256 hashes
- `experiment/phase2/CURRENT_STATE.md` — This file

### Modified
- `experiment/phase2/parallel_gen.sh` — Env var, no hardcoded key
- `experiment/phase2/sweep_seeds12.sh` — Env var, fixed paths

### Backed Up
- `experiment/phase2/parallel_gen.sh.backup`
- `experiment/phase2/sweep_seeds12.sh.backup`

### Copied to Repo
- 24 seed 1 JSON files from `E:\artifacts\phase2\gen\` → `artifacts/phase2/gen/`

---

## Confirmatory Outcome Status

**UNTOUCHED ✓**

No one has examined:
- Task-level outcomes on split_p2_test
- Repair/harm rates
- Oracle headroom
- D−A contrast
- Builder/target effects
- Routing performance

**This is the correct state for a pre-registered study.**

---

## Summary

**Current state is CLEAN:**
- API keys removed from scripts ✓
- Seed 1 files recovered and manifested ✓
- True generation status documented (49/72, 12/18 paired) ✓
- P0 blockers identified and documented ✓
- Confirmatory outcomes still untouched ✓

**Waiting for user input on:**
1. New API key (to run seed 2)
2. Budget path selection (A/B/C)
3. Git history decision (scrub or accept)

**Once user decides → can proceed to protocol freeze → confirmatory evaluation**
