# A provider instrument pilot — 2026-09-12

This is a bounded provider instrument pilot for the revised A runtime. It is
not a confirmatory estimate of stable complementarity and cannot close the
reviewer's real-versus-clone evidence requirement by itself.

## Frozen inputs

- Task split: `experiment/phase2/split_A_pilot_20.json`, 20 tasks from the
  pre-drawn 400-item core, selected by the recorded SHA-256 rule before this
  run. Split SHA-256: `28824da5a66ba986d59d86b8a7e416775afe43a3489e91f2d9367df71d5d60c8`.
- Target: `GLM-5.3-Flash` through the configured Paratera endpoint,
  temperature 0, cache mode off, no status retries, 120-second request timeout.
- Repeats: 0, 1, 2, 3. The same five members are run in every repeat.
- Members: `bare`; two frozen historical Phase-II candidates
  (`p2_A_deepseek_s0_g0`, `p2_A_qwen_s0_g0`); and one same-source clone for
  each candidate. Clone members have distinct identities and scheduling keys
  but the exact same source bytes as their paired real member.
- Scheduling: interleaved SHA-256 task/member order from
  `experiment/revision/interleaved_collect.py`; order is fixed before results
  and does not depend on correctness.

## Resource contract

Every cell has the same pre-request limits: at most 8 logical solver calls, 8
requested samples, 32,768 requested output tokens, and 1,000,000 cumulative
request-body bytes. The runtime rejects a request before sending it when a
limit would be exceeded. Actual provider usage, request IDs, latency, failures,
unknown completions, and pending cells remain in the ledger.

The pilot stops on an unresolved worker, unknown provider completion, missing
usage, or an unfinished request. It does not retry or fill missing cells. A
successful output is valid only if all 400 cells finish, source/data hashes
remain unchanged, and the manifest and event ledger pass the runtime checks.

## Analysis boundary

If complete, report cell completion, actual resource use, within-source repeat
disagreement, and descriptive real-versus-same-source-clone contrasts. Do not
report `H_stable`, a selector benefit, a population-level real-versus-clone
effect, or a superiority claim from this 20-task pilot. The 200-task A pilot
and a newly generated common raw pool remain required for the confirmatory
review response.
