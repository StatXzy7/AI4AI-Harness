"""Fresh Gate-v4 reference controls for premeasurement static review."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Protocol


class ControlIO(Protocol):
    schema: str

    def llm(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.0,
        n: int = 1,
    ) -> str | list[str]: ...

    def execute(self, sql: str) -> dict[str, Any]: ...


Solve = Callable[[ControlIO, str], str]


def _extract_sql(value: object) -> str:
    text = "" if value is None else str(value)
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    return (match.group(1) if match else text).strip()


def _responses(value: str | list[str], count: int) -> list[str]:
    items = value if isinstance(value, list) else [value]
    normalized = [_extract_sql(item) for item in items[:count]]
    normalized.extend([""] * (count - len(normalized)))
    return normalized


def _feedback(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)


def _rows_key(rows: object) -> str:
    return json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    )


def _majority_by_rows(
    candidates: list[str], results: list[dict[str, Any]]
) -> str:
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for index, result in enumerate(results):
        if not result.get("ok"):
            continue
        key = _rows_key(result.get("rows", []))
        counts[key] = counts.get(key, 0) + 1
        first_seen.setdefault(key, index)
    if not counts:
        return candidates[0]
    winner = max(counts, key=lambda key: (counts[key], -first_seen[key]))
    return candidates[first_seen[winner]]


def _first_nonempty(
    candidates: list[str], results: list[dict[str, Any]]
) -> str:
    first_ready = bool(results[0].get("ok")) and bool(results[0].get("rows"))
    second_ready = bool(results[1].get("ok")) and bool(results[1].get("rows"))
    if first_ready:
        return candidates[0]
    if second_ready:
        return candidates[1]
    return candidates[0]


def _hint_body(question: str) -> str:
    match = re.search(r"\bHint\s*:\s*(.+)", question, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _two_step_plan(value: object) -> tuple[str, str]:
    text = "" if value is None else str(value)
    match = re.search(r"\[[\s\S]*?\]", text)
    candidate = match.group(0) if match else text
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        parsed = []
    steps = [str(item) for item in parsed[:2]] if isinstance(parsed, list) else []
    while len(steps) < 2:
        steps.append(f"Unresolved step {len(steps) + 1}")
    return steps[0], steps[1]


def _schema_selection(value: object) -> dict[str, object] | None:
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("tables"), list):
        return None
    cleaned_tables: list[dict[str, object]] = []
    for table in parsed["tables"]:
        if not isinstance(table, dict):
            return None
        name = table.get("name")
        columns = table.get("columns")
        if not isinstance(name, str) or not isinstance(columns, list):
            return None
        if not all(isinstance(column, str) for column in columns):
            return None
        cleaned_tables.append({"name": name, "columns": columns})
    return {"tables": cleaned_tables}


def _selection_payload(value: object) -> str:
    parsed = _schema_selection(value)
    if parsed is not None:
        return json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    return json.dumps(
        {"status": "invalid", "raw_linker_response": str(value)},
        ensure_ascii=False,
        sort_keys=True,
    )


def _selection_lines(value: object) -> str:
    parsed = _schema_selection(value)
    if parsed is None:
        return "INVALID_SELECTION: recompute a restricted allowlist before writing SQL"
    lines = []
    for table in parsed["tables"]:
        columns = ", ".join(table["columns"])
        lines.append(f"{table['name']}({columns})")
    return "\n".join(lines)


def _local_error_class(result: dict[str, Any]) -> str:
    text = str(result.get("error") or "").lower()
    schema_signals = (
        "schema failure",
        "no such table",
        "no such column",
        "unknown table",
        "unknown column",
    )
    syntax_signals = ("syntax", "parse", "incomplete input", "near ")
    if any(signal in text for signal in schema_signals):
        return "schema"
    if any(signal in text for signal in syntax_signals):
        return "syntax"
    return "semantics"


def _repair_action(kind: str) -> str:
    actions = {
        "syntax": "Repair SQL grammar and token placement while preserving the task intent.",
        "schema": "Replace invalid identifiers using only tables and columns in the schema.",
        "semantics": "Revise joins, filters, or aggregation so the query represents the task intent.",
    }
    return actions.get(
        kind,
        "The category was unresolved; inspect the exact feedback before repairing the SQL.",
    )


def control_aurora(io: ControlIO, question: str) -> str:
    draft = _extract_sql(
        io.llm(
            "Create one SQLite query.\n"
            f"Database schema:\n{io.schema}\n"
            f"User question:\n{question}"
        )
    )
    outcome = io.execute(draft)
    if outcome.get("ok"):
        return draft
    repaired = io.llm(
        "Repair the failed query from the complete execution record.\n"
        f"Database schema:\n{io.schema}\n"
        f"User question:\n{question}\n"
        f"Failed SQL:\n{draft}\n"
        f"Exact execution feedback:\n{_feedback(outcome)}"
    )
    return _extract_sql(repaired)


def control_maple(io: ControlIO, question: str) -> str:
    request = {
        "task": question,
        "schema": io.schema,
        "instruction": "Return one SQLite query.",
    }
    candidate = _extract_sql(
        io.llm("SQL request JSON:\n" + json.dumps(request, ensure_ascii=False))
    )
    execution = io.execute(candidate)
    if execution.get("ok"):
        return candidate
    repair_record = {
        "schema": io.schema,
        "question": question,
        "previous_sql": candidate,
        "exact_execution_feedback": execution,
    }
    return _extract_sql(
        io.llm(
            "Correct the SQL using every field in this failure record:\n"
            + json.dumps(repair_record, ensure_ascii=False, default=str)
        )
    )


def control_cobalt(io: ControlIO, question: str) -> str:
    candidate = _extract_sql(
        io.llm(
            "Draft one SQLite query.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    execution = io.execute(candidate)
    if execution.get("ok"):
        return candidate
    return _extract_sql(
        io.llm(
            "Repair the previous SQL.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"Previous SQL:\n{candidate}"
        )
    )


def control_coral(io: ControlIO, question: str) -> str:
    candidate = _extract_sql(
        io.llm(
            "Draft one SQLite query.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    execution = io.execute(candidate)
    return _extract_sql(
        io.llm(
            "Review and rewrite the previous SQL using the execution record.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"Previous SQL:\n{candidate}\n"
            f"Exact execution feedback:\n{_feedback(execution)}"
        )
    )


def control_raven(io: ControlIO, question: str) -> str:
    candidates = _responses(
        io.llm(
            "Generate three independently sampled SQLite candidates.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}",
            temperature=0.35,
            n=3,
        ),
        3,
    )
    results = [io.execute(candidate) for candidate in candidates]
    return _majority_by_rows(candidates, results)


def control_onyx(io: ControlIO, question: str) -> str:
    approaches = (
        "Begin from the entities named in the question.",
        "Begin from the requested output and work backward through joins.",
        "Build the query by validating filters before aggregation.",
    )
    candidates = [
        _extract_sql(
            io.llm(
                f"{approach}\nSchema:\n{io.schema}\nQuestion:\n{question}",
                temperature=0.2,
            )
        )
        for approach in approaches
    ]
    results = [io.execute(candidate) for candidate in candidates]
    return _majority_by_rows(candidates, results)


def control_mica(io: ControlIO, question: str) -> str:
    candidates = _responses(
        io.llm(
            "Generate three SQLite candidates.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}",
            temperature=0.35,
            n=3,
        ),
        3,
    )
    results = [io.execute(candidate) for candidate in candidates]
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for index, candidate in enumerate(candidates):
        counts[candidate] = counts.get(candidate, 0) + 1
        first_seen.setdefault(candidate, index)
    winner = max(counts, key=lambda sql: (counts[sql], -first_seen[sql]))
    return winner if results else candidates[0]


def control_pebble(io: ControlIO, question: str) -> str:
    candidates = _responses(
        io.llm(
            "Generate three SQLite candidates.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}",
            temperature=0.35,
            n=3,
        ),
        3,
    )
    results = [io.execute(candidate) for candidate in candidates]
    for candidate, result in zip(candidates, results, strict=True):
        if result.get("ok"):
            return candidate
    return candidates[0]


def control_orchid(io: ControlIO, question: str) -> str:
    linked = io.llm(
        "Select the schema identifiers relevant to the task.\n"
        "Response type: JSON only.\n"
        'Required shape: {"tables":[{"name":"table","columns":["column"]}]}\n'
        f"Original schema:\n{io.schema}\n"
        f"Question:\n{question}"
    )
    payload = _selection_payload(linked)
    return _extract_sql(
        io.llm(
            "Write one SQLite query under this binding identifier boundary.\n"
            "Use only table and column identifiers in Selected schema JSON.\n"
            "If its status is invalid, recompute a restricted allowlist before SQL; do not "
            "treat invalid input as permission to use every identifier.\n"
            f"Selected schema JSON:\n{payload}\n"
            f"Original schema for identifier verification:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )


def control_birch(io: ControlIO, question: str) -> str:
    linked = io.llm(
        "Return the relevant tables and columns as typed JSON.\n"
        'JSON contract: {"tables":[{"name":"...","columns":["..."]}]}\n'
        f"Schema catalog:\n{io.schema}\n"
        f"Question:\n{question}"
    )
    allowlist = _selection_lines(linked)
    return _extract_sql(
        io.llm(
            "Construct SQL using the binding allowlist below. No identifier outside it may "
            "appear unless INVALID_SELECTION explicitly requires recomputing a restricted "
            "allowlist first.\n"
            f"Binding allowlist:\n{allowlist}\n"
            f"Original schema for validation:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )


def control_quartz(io: ControlIO, question: str) -> str:
    linked = io.llm(
        "Return relevant tables and columns as JSON.\n"
        'Shape: {"tables":[{"name":"...","columns":["..."]}]}\n'
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    )
    payload = _selection_payload(linked)
    return _extract_sql(
        io.llm(
            "Write one SQLite query. The linked payload is advisory; use any identifier from "
            "the full schema when convenient.\n"
            f"Advisory linked JSON:\n{payload}\n"
            f"Full schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )


def control_spruce(io: ControlIO, question: str) -> str:
    io.llm(
        "Return relevant tables and columns as JSON.\n"
        'Shape: {"tables":[{"name":"...","columns":["..."]}]}\n'
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    )
    return _extract_sql(
        io.llm(
            "Write one SQLite query from the complete schema.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )


def control_lotus(io: ControlIO, question: str) -> str:
    hint = _hint_body(question)
    parts = [
        "Produce one SQLite query.",
        f"Original schema:\n{io.schema}",
        f"Original question:\n{question}",
    ]
    if hint:
        parts.append(f"Mandatory constraint taken from the Hint:\n{hint}")
    return _extract_sql(io.llm("\n".join(parts)))


def control_saffron(io: ControlIO, question: str) -> str:
    hint = _hint_body(question)
    instruction = "Return one SQLite query."
    if hint:
        instruction = f"The following Hint content must be satisfied: {hint}\n{instruction}"
    prompt = (
        f"Schema exactly as supplied:\n{io.schema}\n"
        f"Question exactly as supplied:\n{question}\n"
        f"{instruction}"
    )
    return _extract_sql(io.llm(prompt, temperature=0.0, n=1))


def control_slate(io: ControlIO, question: str) -> str:
    return _extract_sql(
        io.llm(
            "Return one SQLite query.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )


def control_fog(io: ControlIO, question: str) -> str:
    hint = _hint_body(question)
    if hint:
        requirement = f"Mandatory Hint constraint:\n{hint}"
    else:
        requirement = "Mandatory constraint: sort the final rows in ascending order."
    return _extract_sql(
        io.llm(
            "Return one SQLite query.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"{requirement}"
        )
    )


def control_pine(io: ControlIO, question: str) -> str:
    direct = _extract_sql(
        io.llm(
            "Construct SQL directly from base tables with explicit joins and filters.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    staged = _extract_sql(
        io.llm(
            "Construct an alternative SQL formulation using CTE stages before the final "
            "projection.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    candidates = [direct, staged]
    results = [io.execute(candidate) for candidate in candidates]
    return _first_nonempty(candidates, results)


def control_breeze(io: ControlIO, question: str) -> str:
    approaches = (
        "Start from the principal entity and attach only required relations.",
        "Start from the requested metric or aggregate and trace backward to entities.",
    )
    candidates = [
        _extract_sql(
            io.llm(
                f"{approach}\nSchema:\n{io.schema}\nQuestion:\n{question}"
            )
        )
        for approach in approaches
    ]
    results = [io.execute(candidate) for candidate in candidates]
    return _first_nonempty(candidates, results)


def control_finch(io: ControlIO, question: str) -> str:
    candidates = _responses(
        io.llm(
            "Return two candidates based on different construction approaches.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}",
            n=2,
        ),
        2,
    )
    results = [io.execute(candidate) for candidate in candidates]
    return _first_nonempty(candidates, results)


def control_marrow(io: ControlIO, question: str) -> str:
    first = _extract_sql(
        io.llm(
            "Use a join-first query construction.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    second = _extract_sql(
        io.llm(
            "Use an aggregation-first query construction.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    candidates = [first, second]
    results = [io.execute(candidate) for candidate in candidates]
    second_ready = bool(results[1].get("ok")) and bool(results[1].get("rows"))
    first_ready = bool(results[0].get("ok")) and bool(results[0].get("rows"))
    if second_ready:
        return second
    if first_ready:
        return first
    return first


def control_jade(io: ControlIO, question: str) -> str:
    plan = io.llm(
        "Return exactly two ordered sub-questions as a JSON array.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    )
    step_one, step_two = _two_step_plan(plan)
    first_answer = io.llm(
        "Answer only the current decomposition step.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Current sub-question to answer:\n{step_one}"
    )
    second_answer = io.llm(
        "Answer only the current decomposition step, using earlier context when useful.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Earlier sub-question:\n{step_one}\n"
        f"Earlier returned answer:\n{first_answer}\n"
        f"Current sub-question to answer:\n{step_two}"
    )
    return _extract_sql(
        io.llm(
            "Assemble one SQLite query from both returned decomposition answers.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"Returned answer 1:\n{first_answer}\n"
            f"Returned answer 2:\n{second_answer}"
        )
    )


def control_iris(io: ControlIO, question: str) -> str:
    steps = _two_step_plan(
        io.llm(
            "Plan two ordered sub-questions and return only their JSON array.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    answers: list[str | list[str]] = []
    for step in steps:
        prior = "\n".join(str(answer) for answer in answers)
        answers.append(
            io.llm(
                "Resolve the current step.\n"
                f"Schema:\n{io.schema}\n"
                f"Question:\n{question}\n"
                f"Earlier returned answers:\n{prior}\n"
                f"Current sub-question to answer:\n{step}"
            )
        )
    return _extract_sql(
        io.llm(
            "Build one SQLite query using both returned partial answers.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"First partial answer:\n{answers[0]}\n"
            f"Second partial answer:\n{answers[1]}"
        )
    )


def control_flint(io: ControlIO, question: str) -> str:
    step_one, step_two = _two_step_plan(
        io.llm(
            "Return two ordered sub-questions as JSON.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    io.llm(
        "Resolve the current step.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Current sub-question to answer:\n{step_one}"
    )
    io.llm(
        "Resolve the current step.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Current sub-question to answer:\n{step_two}"
    )
    return _extract_sql(
        io.llm(
            "Build one SQLite query from the two planned step names.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"Planned step 1:\n{step_one}\n"
            f"Planned step 2:\n{step_two}"
        )
    )


def control_delta(io: ControlIO, question: str) -> str:
    step_one, step_two = _two_step_plan(
        io.llm(
            "Return two ordered sub-questions as JSON.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    second_answer = io.llm(
        "Resolve the current step.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Current sub-question to answer:\n{step_two}"
    )
    first_answer = io.llm(
        "Resolve the current step.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Current sub-question to answer:\n{step_one}"
    )
    return _extract_sql(
        io.llm(
            "Assemble one SQLite query from both returned answers.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"Returned answer for step 1:\n{first_answer}\n"
            f"Returned answer for step 2:\n{second_answer}"
        )
    )


def control_cedar(io: ControlIO, question: str) -> str:
    candidate = _extract_sql(
        io.llm(
            "Write one SQLite query.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    result = io.execute(candidate)
    if result.get("ok"):
        return candidate
    kind = _local_error_class(result)
    return _extract_sql(
        io.llm(
            f"Failure category: {kind}\n"
            f"Required action: {_repair_action(kind)}\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"Previous SQL:\n{candidate}\n"
            f"Exact execution feedback:\n{_feedback(result)}"
        )
    )


def control_lantern(io: ControlIO, question: str) -> str:
    candidate = _extract_sql(
        io.llm(
            "Write one SQLite query.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    result = io.execute(candidate)
    if result.get("ok"):
        return candidate
    category_reply = io.llm(
        "Return exactly one category: syntax, schema, or semantics.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Failed SQL:\n{candidate}\n"
        f"Exact execution feedback:\n{_feedback(result)}"
    )
    kind = str(category_reply).strip().lower()
    return _extract_sql(
        io.llm(
            f"Consumed category: {kind}\n"
            f"Required action: {_repair_action(kind)}\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"Previous SQL:\n{candidate}\n"
            f"Exact execution feedback:\n{_feedback(result)}"
        )
    )


def control_ember(io: ControlIO, question: str) -> str:
    candidate = _extract_sql(
        io.llm(
            "Write one SQLite query.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    result = io.execute(candidate)
    if result.get("ok"):
        return candidate
    kind = _local_error_class(result)
    return _extract_sql(
        io.llm(
            f"Failure category: {kind}\n"
            "Required action: Rewrite the SQL more carefully.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"Previous SQL:\n{candidate}\n"
            f"Exact execution feedback:\n{_feedback(result)}"
        )
    )


def control_elm(io: ControlIO, question: str) -> str:
    candidate = _extract_sql(
        io.llm(
            "Write one SQLite query.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}"
        )
    )
    result = io.execute(candidate)
    if result.get("ok"):
        return candidate
    io.llm(
        "Return exactly one category: syntax, schema, or semantics.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Failed SQL:\n{candidate}\n"
        f"Exact execution feedback:\n{_feedback(result)}"
    )
    return _extract_sql(
        io.llm(
            "Rewrite the SQL more carefully.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"Previous SQL:\n{candidate}\n"
            f"Exact execution feedback:\n{_feedback(result)}"
        )
    )


def control_harbor(io: ControlIO, question: str) -> str:
    return _extract_sql(
        io.llm(
            "Return exactly one ```sql fenced block and no text outside the fence.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}",
            n=1,
        )
    )


def control_nova(io: ControlIO, question: str) -> str:
    return _extract_sql(
        io.llm(
            "Use the supplied schema and question. Output only one fenced SQL block, with "
            "the fence language set to sql and no explanation.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}",
            system="Your entire answer must be one ```sql fenced block with no extra prose.",
            n=1,
        )
    )


def control_willow(io: ControlIO, question: str) -> str:
    return _extract_sql(
        io.llm(
            "Return raw SQLite text only, without a markdown fence or explanation.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}",
            n=1,
        )
    )


def control_umber(io: ControlIO, question: str) -> str:
    return _extract_sql(
        io.llm(
            "Explain the approach, then provide one ```sql fenced block, then add a short "
            "verification note.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}",
            n=1,
        )
    )


CASES: list[dict[str, str | Solve | None]] = [
    {"case_id": "gv4r001", "strategy": "schema_link", "solve": control_orchid},
    {"case_id": "gv4r002", "strategy": "repair", "solve": control_cobalt},
    {"case_id": "gv4r003", "strategy": "error_classify", "solve": control_lantern},
    {"case_id": "gv4r004", "strategy": "vote3", "solve": control_mica},
    {"case_id": "gv4r005", "strategy": "hint_guard", "solve": control_saffron},
    {"case_id": "gv4r006", "strategy": "decompose", "solve": control_delta},
    {"case_id": "gv4r007", "strategy": "format_guard", "solve": control_harbor},
    {"case_id": "gv4r008", "strategy": "two_view", "solve": control_finch},
    {"case_id": "gv4r009", "strategy": "repair", "solve": control_maple},
    {"case_id": "gv4r010", "strategy": "schema_link", "solve": control_quartz},
    {"case_id": "gv4r011", "strategy": "vote3", "solve": control_raven},
    {"case_id": "gv4r012", "strategy": "error_classify", "solve": control_ember},
    {"case_id": "gv4r013", "strategy": "two_view", "solve": control_pine},
    {"case_id": "gv4r014", "strategy": "hint_guard", "solve": control_slate},
    {"case_id": "gv4r015", "strategy": "decompose", "solve": control_iris},
    {"case_id": "gv4r016", "strategy": "format_guard", "solve": control_willow},
    {"case_id": "gv4r017", "strategy": "vote3", "solve": control_pebble},
    {"case_id": "gv4r018", "strategy": "repair", "solve": control_aurora},
    {"case_id": "gv4r019", "strategy": "schema_link", "solve": control_birch},
    {"case_id": "gv4r020", "strategy": "error_classify", "solve": control_cedar},
    {"case_id": "gv4r021", "strategy": "hint_guard", "solve": control_lotus},
    {"case_id": "gv4r022", "strategy": "two_view", "solve": control_marrow},
    {"case_id": "gv4r023", "strategy": "format_guard", "solve": control_nova},
    {"case_id": "gv4r024", "strategy": "decompose", "solve": control_flint},
    {"case_id": "gv4r025", "strategy": "schema_link", "solve": control_spruce},
    {"case_id": "gv4r026", "strategy": "vote3", "solve": control_onyx},
    {"case_id": "gv4r027", "strategy": "repair", "solve": control_coral},
    {"case_id": "gv4r028", "strategy": "error_classify", "solve": control_elm},
    {"case_id": "gv4r029", "strategy": "two_view", "solve": control_breeze},
    {"case_id": "gv4r030", "strategy": "format_guard", "solve": control_umber},
    {"case_id": "gv4r031", "strategy": "decompose", "solve": control_jade},
    {"case_id": "gv4r032", "strategy": "hint_guard", "solve": control_fog},
]
