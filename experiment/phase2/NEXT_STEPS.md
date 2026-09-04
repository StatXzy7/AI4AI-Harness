# Phase-II Immediate Action Items

## Current Status (2026-09-05 evening)

**Generation:** 24/72 runs complete (seed 0 done for 6 builders × 4 arms)
- Running in background via `parallel_gen.sh` (4 workers)
- Monitor: `python experiment/phase2/monitor_gen.py`
- ETA: 12–18 hours for all 72 runs (seeds 1 and 2 in progress)

**Evaluation infrastructure:** Complete and committed
- `queue_evaluation.py` — builds manifest with A/D pairing enforcement
- `outcome_table.py` — computes SAP estimands + D−A contrast
- `run_confirmatory.sh` — end-to-end pipeline
- `official_scorer.py` — BIRD judge re-scoring (timeout fixed)

**Blocking issues identified:** 7 (see REVIEWER_ATTACKS.md)
**Corrected protocols:** SAP v2.0 written, ready to freeze

---

## Tomorrow Morning (Sept 6)

### 1. Check generation completion
```bash
python experiment/phase2/monitor_gen.py
# Should show 72/72 logs when done
```

### 2. Audit yield table
```bash
python experiment/phase2/yield_table.py
# Target: 18 paired (builder, seed) cells with both A and D present
```

If < 18 cells: identify which builder/seed failed, debug or drop that builder.

### 3. Freeze protocol v2.0
```bash
cd experiment/phase2
git add SAP_v2.md REVIEWER_ATTACKS.md CROSS_DOMAIN_PLAN.md
git commit -m "Phase-II protocol v2.0 — blocking fixes from Codex audit"
# Generate SHA256 of frozen state
git rev-parse HEAD > PROTOCOL_HASH.txt
cat PROTOCOL_HASH.txt  # This is your immutable timestamp
```

**CRITICAL:** Do NOT look at confirmatory outcomes before this commit.

---

## Decision Point: Budget Approval

The reviewer attack surface requires ~$26K to fully address:
- New 1000-task confirmatory set: $12K
- 3-seed replication: $1.5K (mostly done)
- Cross-domain (SWE-bench): $6.5K
- 4-target transfer: $3K
- Cache sensitivity: $0.8K
- Routing deep-dive: $2K

**Minimum viable (blocking only):** $14.8K

**USER MUST DECIDE:**
- Full defense ($26K) → strong 7/10 paper
- Blocking only ($15K) → defensible 6/10 paper
- Abort expensive fixes → 5/10 borderline reject

**Request user input before proceeding.**

---

## If User Approves Full Budget

### Week 1 (Sept 6–12): BIRD Confirmatory

**Day 1-2 (Sept 6–7):**
- Generate new 1000+ task split from completely untouched databases
- Verify touched_registry shows `"complete": true`
- Run cache sensitivity analysis (200 tasks, 3 repeats, $800)

**Day 3-4 (Sept 8–9):**
- Collect BIRD confirmatory matrix (1169 tasks × ~100 harnesses, $12K)
- Official re-scoring
- Generate primary table

**Day 5 (Sept 10):**
- Arm E analysis (6 builders × 3 seeds, already generated)
- Builder generalization table
- Target transfer evaluation (4 targets × D population, $3K)

**Day 6-7 (Sept 11–12):**
- Routing experiments (task/db/harness/joint holdout, LLM baseline, $2K)
- Bootstrap CIs
- Freeze all BIRD results

---

### Week 2 (Sept 13–19): Cross-Domain

**Day 8-9 (Sept 13–14):**
- SWE-bench Verified infrastructure
- 200-task split
- Harness scaffold adaptation

**Day 10-11 (Sept 15–16):**
- Phase 1 (collapse discovery, $800)
- Phase 2 (forced diversity, $4.8K)

**Day 12-13 (Sept 17–18):**
- Human positive control ($600)
- Cross-domain table

**Day 14 (Sept 19):**
- ICLR abstract submission (DEADLINE)

---

### Week 3 (Sept 20–25): Paper Writing

**Day 15-17 (Sept 20–22):**
- Main tables + figures
- Sections 4–7 (Discovery, Factorial, Generalization, Routing)
- Method + Results sections

**Day 18-19 (Sept 23–24):**
- Adversarial reviewer audit (simulate attacks, patch holes)
- Full reproduction: raw data → tables/figures in one script
- Intro + Discussion + Limitations

**Day 20 (Sept 25):**
- Final submission to ICLR

---

## If User Declines Full Budget (Blocking Only)

**Minimum path:**
1. Use current 72-run generation (done by tomorrow)
2. Skip new confirmatory set — relabel 151 pilot as "development", report limitations
3. Collect on existing split ($3K for full matrix)
4. Skip cross-domain entirely — acknowledge single-domain limitation
5. Skip 4-target transfer — report GLM-only results
6. Basic routing (task-held-out AUROC only)

**Result:** Submittable but weak. Reviewers will note all the skipped validations.
**Expected score:** 5–6/10 (borderline)

---

## If Generation Fails to Reach 18 Cells

**Fallback:** Reduce to 4 builders (GLM, Qwen, DeepSeek, one frontier model), rerun seeds 1-2
for missing cells, accept 12 paired cells as minimum viable.

**Impact:** "Builder generalization" claim becomes much weaker.

---

## Critical Path Dependencies

```
Generation (72 runs)
  └─> Yield audit (18 cells?)
       ├─> [PASS] Protocol freeze → Confirmatory evaluation
       └─> [FAIL] Debug/rerun → Delay 2-3 days

Confirmatory matrix
  └─> Primary table (D−A contrast)
       ├─> [Positive] Write victory lap
       └─> [Negative/Null] Pivot to "diversity necessary but insufficient" framing

Cross-domain replication
  └─> [Replicates] → Strong generalization claim
  └─> [Fails] → Boundary result (mechanism-specific)
```

---

## Open Questions for User

1. **Budget approval:** Full $26K, blocking $15K, or minimal $3K?
2. **Submission target:** Definitely ICLR 2027 (abstract due Sept 19, full paper Sept 25)?
3. **Author list:** Finalized? (Cannot change after abstract submission)
4. **Cross-domain priority:** Must-have or nice-to-have?
5. **Risk tolerance:** Willing to submit with acknowledged limitations, or hold for perfect defense?

**User should answer these BEFORE confirmatory evaluation starts.**

---

## Contact Points

- Generation progress: `python experiment/phase2/monitor_gen.py`
- Yield status: `python experiment/phase2/yield_table.py`
- Confirmatory pipeline: `bash experiment/phase2/run_confirmatory.sh`
- Blocking issues: `experiment/phase2/REVIEWER_ATTACKS.md`
- Cross-domain plan: `experiment/phase2/CROSS_DOMAIN_PLAN.md`
- Updated protocol: `experiment/phase2/SAP_v2.md`

**Next human input needed: Budget and timeline approval.**
