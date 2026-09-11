# Qwen timeout continuation design 01

Status: DRAFT — no provider calls authorized by this document alone.

## Evidence requiring continuation
The frozen Qwen pool stopped at attempt 157 with 22/96 completed, one ReadTimeout whose provider completion and cost are unknown, and 73 unstarted attempts. The original directory remains immutable. Evidence: `common_pool_qwen_continuation/incomplete_audit.json`.

## Scientific boundary
The 22 completed responses are retained for provenance only. They cannot be analyzed as a complete common pool and cannot support quality, superiority, or cost claims. The unknown request remains an unresolved expenditure item and is never silently retried or counted as zero.

## Proposed continuation
Create a new pool directory and new pool id. Reuse only the 73 never-started logical attempts from the frozen manifest, with their exact request bodies, identities, order, and three-attempt denominator. Do not resend the 22 completed attempts or the unknown attempt. The resulting dataset must be labeled a partial continuation and must not be merged into the original pool unless an independently reviewed merge audit proves identity, denominator, and missingness invariants.

Use a separately frozen manifest binding the source hashes, selected task identities, request-body hashes, provider model, timeout, and budget ceiling. Use a shorter per-request timeout only if the provider's completion semantics and unknown-cost handling are unchanged. Any new transport, response, or usage uncertainty stops the continuation and writes a new incomplete audit. No automatic retries, candidate execution, gate calls, benchmark calls, or post hoc task substitution are allowed.

## Acceptance gate
A continuation may enter paired extraction analysis only if every originally planned logical attempt is represented exactly once across the preserved completed prefix, preserved unknown attempt, and continuation records; all response bytes and usage are known except explicitly retained unknowns; and an independent audit verifies the resulting denominator. If any unknown remains, report missingness and do not claim a complete pool.

## Required review before launch
1. Independent mechanical review of the selection and merge manifest.
2. Independent specification review of timeout, missingness, and denominator wording.
3. A cost ceiling check using actual provider billing evidence where available; requested `max_tokens` is not a verified billing bound.
4. User-visible launch record with the new directory and immutable bindings.
