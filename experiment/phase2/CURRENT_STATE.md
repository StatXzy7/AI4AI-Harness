# Phase-II Current State

**Real date:** 2026-09-04 (late afternoon). Factual, no aspirational claims.

## What just happened

The Codex re-review rejected commit `48fa0a6` (score 2/10). Its findings were correct: the
"fix" reports re-committed the API key in plaintext; the rewritten scripts passed a
nonexistent `--out` flag and would have failed at argparse; they would have re-run and
overwritten the recovered seed 1; and "paused at clean baseline" was false — generation
processes were still running and had already rewritten one artifact.

Since then (this working session):

1. **All generation queues stopped** — 11 processes (two overlapping sweep queues plus their
   children, including seed-2 units mid-flight). Pre-stop state snapshotted to
   `artifacts/phase2/state_snapshots/pre_fix_*.json`. Nothing deleted or overwritten.
2. **Credential redacted from every working-tree file** (reports and backups); the broken
   `.backup` files deleted outright; secret scan over the tracked tree returns CLEAN
   (filenames-only scan; untracked `.env*` verified untracked).
   **The exposed key is still live until the user revokes it on the provider. That is the
   single outstanding user action. No new credential has been given to any script.**
3. **Broken scripts replaced** by one entrypoint, `experiment/phase2/gen_seed2.sh`: uses the
   real `--log` flag; JSON naming `A_<builder>_s<seed>.json` (compatible with
   monitor/yield tools); runs seed 2 only; skips existing valid targets; treats corrupt
   partials as absent; publishes atomically via temp-file rename; propagates Python failures
   as non-zero exit. Dry-run verified 24/24 units, zero API calls.
4. **Seed-1 reconciliation** (`seed1_reconciliation.json`): 23/24 units source/repo identical
   by SHA-256/size/mtime. `D_glm_s1.json` diverged because a still-running duplicate queue
   rewrote the external copy at 16:09:06, after the 16:05 recovery. Both versions quarantined
   (`artifacts/phase2/quarantine/D_glm_s1/`); canonical = repo version per the
   earliest-complete-finish rule, *not* by K_admitted (it is the K=2 version, proving the
   rule is not outcome-based). Decision recorded in `DECISION.md` alongside both files.
5. **Partial seed-2 raw dirs** from the killed runs archived to
   `artifacts/phase2/quarantine/seed2_partial_killed_runs/` (units never completed; no JSON
   log; raw files unreferenced).
6. **Protocols merged**: `PHASE2_FREEZE.md`, `PHASE2_SAP.md`, `experiment/phase2/SAP_v2.md`
   are tombstones; **`PHASE2_PROTOCOL.md` is the single authority**, with the complete
   deviation changelog (D1–D11) and the real freeze anchor in `PROTOCOL_FREEZE.txt`.

## Generation status (factual)

| Track | Seed 0 | Seed 1 | Seed 2 | Total |
|---|---|---|---|---|
| **A–D (factorial)** | 24/24 | 24/24 | 0/24 | **48/72** |
| **Arm E (separate)** | 1 run (deepseek) | 0 | 0 | 1 |

All JSON logs validated parseable. Paired (builder×seed) cells with both A and D: **12/18**.
Seed 2 requires a valid environment credential; run `gen_seed2.sh` when available.

Arm E is counted separately and never enters the 72-unit factorial grid.

## Confirmatory outcomes

**None examined.** No `split_p2_test` evaluation has been run (the only contact with test
items is the disclosed 18-item smoke, deviation D1). No D−A contrast computed. This claim is
accurate as of the freeze commit and re-affirmed in `PHASE2_PROTOCOL.md` §preamble.

## Outstanding user actions

1. **Revoke the exposed Paratera key on the provider** (the only blocking user action).
2. Decide on git-history handling for the leaked key (rotation is the effective remedy
   either way; scrubbing is optional).
3. After revocation + new key in environment: approve running `gen_seed2.sh` (24 units,
   seed 2 only).

Budget-path selection (A/$26K, B/$15K, C/$3K) is explicitly **deferred** until the minimal
defensible main experiment (A–D × 6 builders × 3 seeds on untouched BIRD, official judge,
frozen D−A continuous effect) is either complete or blocked. No cross-domain work starts
before that closes.
