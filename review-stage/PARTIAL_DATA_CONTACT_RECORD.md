# Prompt-2 factual record: the "partial-data pipeline validation" (commit 2d28fc3 message)

## What happened (verifiable facts)

1. On 2026-09-05, `analysis_primary.py` was run ONCE with `--allow-partial --n-boot 200
   --n-perm 200 --out artifacts/phase2/analysis_structure_check.json` to validate that the
   frozen analysis code executes end-to-end (bootstrap packing, permutation, K-curve
   mechanics) BEFORE the full data arrived.
2. At that time the AD shards held ~56 of 175 harnesses with full 1169-task coverage.
3. The run printed one line of aggregate output (a D-A headroom point estimate over the
   partial cells) and wrote `analysis_structure_check.json`.
4. The partial output file was **deleted within the same session, before any commit**
   (git log confirms `analysis_structure_check.json` was never committed to any ref).
5. The point estimate from partial data was NEVER used in the paper, any status document,
   or any decision. The paper's section 5 remains pending skeletons.
6. The analysis pipeline itself was then modified to fix a real bug found in this test
   (headroom_delta tuple-unpacking) -- i.e., the test did exactly its job: it found a
   crash bug before the real analysis.

## Interpretation (for the deviation log)

- This is a **code-validation run on real partial Phase-II data**, not synthetic data.
- One aggregate number (D-A point estimate over ~1/3 of cells) was transiently printed
  and then discarded; it was not recorded anywhere durable.
- Under the freeze discipline this counts as **observer contact with a partial
  confirmatory aggregate**, before deletion. It is disclosed here rather than claimed
  never to have happened. The frozen primary analysis remains un-run on complete data.
- Whether this contact could bias later analysis is a judgment call for the authors;
  the practical safeguards are that (a) the estimate was never written down, (b) the
  analysis code is frozen under git, (c) the primary contrast is fully pre-specified,
  and (d) the number was computed from a non-representative ~32% subset of cells whose
  selection was determined by collector scheduling, not by outcome.
