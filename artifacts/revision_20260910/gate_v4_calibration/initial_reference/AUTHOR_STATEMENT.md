# Gate-v4 reference-control author statement

- Author model: `gpt-5.6-sol`.
- Role: reference-control author for premeasurement static review; not the future independent static reviewer or measurement executor.
- Prior-experience disclosure: this author previously reviewed the exposed Gate-v3 controls and the stage21 classification-action regression. The author therefore has prior knowledge of old failure patterns and does not claim historical-context independence.
- Construction claim: the 32 Gate-v4 controls were newly written against `review-stage/GATE_V4_CONTRACT.md` and the public `SQLHarness` interface. They are not copies of old controls, renamed old functions, or mutations selected from measurement results.
- Read boundary: project reads were limited to `review-stage/GATE_V4_CONTRACT.md`, `AGENTS.md`, `CLAUDE.md`, and `external/TTHE/text_to_sql/harness_base.py`. The author did not read `gate_v4.py`, measurement implementations, runners, new packets, diagnostics, labels from another author, or new regression results.
- Execution boundary: no gate, evaluate command, provider request, benchmark, or real API was run. Local checks were limited to Python AST parsing and an in-memory `MockIO` interface exercise of the newly authored callables.
- Revision record: one source repair replaced the provisional decomposition field label with the public profile's exact `Current sub-question to answer:` field. No measured behavior was available during that repair.
- Contract question: the author reference proposes routing residual SQLite integer-overflow execution errors to the semantics action because they are neither identifier-resolution nor grammar/parse failures. This is disclosed for independent review and does not treat overflow as a detected wrong answer or establish model classification accuracy.
- Status: author labels are fallible references. The controls and labels await independent static review before any freeze or first measurement.
