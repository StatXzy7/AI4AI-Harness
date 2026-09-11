# Public callable and mechanism contract for independent controls

This document defines the finite synthetic interface under study, without exposing the instrument implementation or earlier controls. Implement the declared mechanism, not a lookup table for a probe or an expected answer. A conforming control need not have new code style or more calls than another strategy.

## Callable interface

Each `solve(io, question)` returns a nonempty SQL string. Only the supplied `io` and pure standard-library computation are available. No filesystem, processes, imports of project modules, network, external services, or gate execution.

- `io.schema` is a string describing tables and columns. Do not assume blank lines separate tables: each table can be on a single line, with adjacent table descriptions on consecutive lines.
- `io.llm(prompt, system='', temperature=0., n=1)` returns text for n=1 and a list of texts for n>1. Text may contain a SQL fence; pure extraction is permitted.
- `io.execute(sql)` returns `{ok: bool, rows: list, error: str | None}`. Execution success can have empty rows. Failed and empty results are not interchangeable.
- For decomposition, the plan reply is a JSON list of ordered subquestion strings, followed by arbitrary textual partial answers. The partial answers cannot be derived from the subquestion strings. Retain actual returned information.
- Synthetic replies exercise observable data flow. They do not establish the semantic correctness of the final SQL on a real benchmark. There is no need to anticipate a particular table, query, token, salt, or probe name.

## Mechanism requirements

| Name | Required behavior |
|---|---|
| repair | Generate initial SQL and execute it. Return on success without unconditional extra generation. On failure, carry exact execution feedback, previous SQL, question and schema into a conditional repair request. No batched extra candidates in this mechanism. |
| vote3 | Generate three candidates, execute all three, and select by the majority of successful execution-result rows, not SQL string counts. Treat equivalent results consistently, including when syntactically different queries have the same rows. |
| schema_link | First identify the tables/columns relevant to the question using the question and schema. Use that returned linked subset in the subsequent SQL request, removing unrelated tables. Calling a linker and then using the full original schema does not suffice. |
| hint_guard | Use one solver sample. Preserve the original schema and question. If the question contains a Hint, restate its actual content as an affirmative hard requirement beyond merely copying it inside the question. With no Hint, preserve the original task without fabricating one. |
| two_view | Make two distinct solver requests that use meaningfully different query-construction approaches, then execute both candidates. Prefer the first successful nonempty result; if it is failed or empty and the second is successful/nonempty, select the second. If both are successful/nonempty, select the first. Whitespace changes or one batched request do not create two formulations. |
| decompose | Request an ordered two-step JSON plan, request an answer to each subquestion in order, and actually use both returned partial answers to assemble final SQL. Earlier subquestions/answers may be included as context for the current subquestion. Merely listing a plan, asking without using answers, or fabricating answers from step names does not suffice. |
| error_classify | Generate and execute initial SQL, return on success. After failure classify the feedback as syntax/schema/semantics and apply an affirmative repair action appropriate to that class, carrying the exact feedback forward. Listing all classes or only changing punctuation/generic retry text is insufficient. An intermediate classification request is permitted; its text need not differ by class. Repair-action semantics must be reviewed separately. |
| format_guard | Use one solver sample, preserve schema and question, and affirmatively require only a fenced SQL answer with no extra prose. A negated or contradictory instruction does not satisfy the mechanism. |

## Review boundary

Prompt keywords and textual similarity do not by themselves establish conformance. Independent source review checks every control against the behavior above. Hint, format, two-view, classification and decomposition also receive a semantic/data-flow review of source plus full synthetic traces. If multiple still-unanswered decomposition steps appear in a request, the instrument may be unable to attribute that request uniquely; preserve uncertainty for independent review rather than assume the code failed. This does not remove independently observable ordering, missing-call or missing-feedback violations.

Review verdicts are `conforms`, `nonconforms`, or `indeterminate`, with exact source/trace evidence. Do not infer real-solver accuracy or semantic diversity from scripted SQL responses. Instrument pass and independent control conformance are separate observations.
