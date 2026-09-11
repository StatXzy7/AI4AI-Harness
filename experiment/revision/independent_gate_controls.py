"""Independent gate-v2 controls authored from the public contract only."""

import json
import re


def _one(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return "" if value is None else str(value)


def _many(value):
    if isinstance(value, list):
        return ["" if item is None else str(item) for item in value]
    return ["" if value is None else str(value)]


def _sql(text):
    value = _one(text).strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", value, re.IGNORECASE | re.DOTALL)
    if fenced:
        value = fenced.group(1).strip()
    match = re.search(r"\b(WITH|SELECT)\b[\s\S]*", value, re.IGNORECASE)
    if match:
        value = match.group(0).strip()
    return value or "SELECT 1"


def _result_key(result):
    if not isinstance(result, dict):
        return ("invalid", repr(result))
    if not result.get("ok"):
        return ("error", str(result.get("error")))
    rows = result.get("rows")
    return ("rows", json.dumps(rows, sort_keys=True, default=str))


def _first_working(candidates, results):
    for candidate, result in zip(candidates, results):
        if isinstance(result, dict) and result.get("ok"):
            return _sql(candidate)
    return _sql(candidates[0] if candidates else "")


def _majority_choice(candidates, results):
    counts = {}
    keys = []
    for result in results:
        key = _result_key(result)
        keys.append(key)
        counts[key] = counts.get(key, 0) + 1
    majority = max(counts, key=counts.get) if counts else None
    for candidate, key in zip(candidates, keys):
        if key == majority:
            return _sql(candidate)
    return _first_working(candidates, results)


def _json_list(text):
    value = _one(text).strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = []
    if isinstance(parsed, list):
        items = [str(item) for item in parsed if str(item).strip()]
        if items:
            return items
    lines = [line.strip(" -\t") for line in value.splitlines() if line.strip(" -\t")]
    return lines[:3] or ["identify the needed tables", "write the final SQL"]


def _linked_schema(schema, payloads):
    schema_text = str(schema)
    words = set()
    for payload in payloads:
        words.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(payload)))
    blocks = [block for block in re.split(r"\n\s*\n", schema_text) if block.strip()]
    kept = []
    for block in blocks:
        names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", block))
        if names & words:
            kept.append(block.strip())
    if kept:
        return "\n\n".join(kept)
    lines = schema_text.splitlines()
    return "\n".join(lines[: max(1, min(len(lines), 12))])


def _classify_error(message):
    text = str(message).lower()
    if any(word in text for word in ("syntax", "parse", "near", "token")):
        return "syntax"
    if any(word in text for word in ("column", "table", "schema", "no such", "unknown")):
        return "schema"
    return "semantics"


def case_001(io, question):
    draft = _sql(io.llm(f"Write one SQL query for this task.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    result = io.execute(draft)
    if isinstance(result, dict) and result.get("ok"):
        return draft
    fixed = io.llm(
        "Repair the SQL using the exact execution feedback. Return only SQL.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nSQL:\n{draft}\nError:\n{result.get('error') if isinstance(result, dict) else result}"
    )
    return _sql(fixed)


def case_002(io, question):
    first = _sql(io.llm(f"Create an initial SQL answer.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    feedback = io.execute(first)
    if isinstance(feedback, dict) and feedback.get("ok"):
        return first
    second = io.llm(
        "The previous SQL failed. Use the database feedback to produce a corrected SQL query only.\n"
        f"Original question:\n{question}\nSchema:\n{io.schema}\nPrevious SQL:\n{first}\nDatabase feedback:\n{feedback}"
    )
    return _sql(second)


def case_003(io, question):
    draft = _sql(io.llm(f"Write SQL for the question.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    io.execute(draft)
    return draft


def case_004(io, question):
    draft = _sql(io.llm(f"Write SQL for the question.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    result = io.execute(draft)
    extra = io.llm(
        f"Give two alternate SQL answers regardless of the prior outcome {result}.\nSchema:\n{io.schema}\nQuestion:\n{question}",
        n=2,
    )
    return _sql(_many(extra)[0])


def case_005(io, question):
    candidates = [_sql(item) for item in _many(io.llm(f"Generate three SQL candidates.\nSchema:\n{io.schema}\nQuestion:\n{question}", n=3))]
    results = [io.execute(candidate) for candidate in candidates]
    return _majority_choice(candidates, results)


def case_006(io, question):
    candidates = [
        _sql(io.llm(f"Approach A: write SQL.\nSchema:\n{io.schema}\nQuestion:\n{question}")),
        _sql(io.llm(f"Approach B: write SQL with a different route.\nSchema:\n{io.schema}\nQuestion:\n{question}")),
        _sql(io.llm(f"Approach C: write SQL after rechecking joins and filters.\nSchema:\n{io.schema}\nQuestion:\n{question}")),
    ]
    results = [io.execute(candidate) for candidate in candidates]
    return _majority_choice(candidates, results)


def case_007(io, question):
    candidates = _many(io.llm(f"Generate three SQL candidates.\nSchema:\n{io.schema}\nQuestion:\n{question}", n=3))
    return _sql(candidates[0])


def case_008(io, question):
    candidates = [_sql(item) for item in _many(io.llm(f"Generate three SQL candidates.\nSchema:\n{io.schema}\nQuestion:\n{question}", n=3))]
    return sorted(candidates, key=lambda item: (len(item), item))[-1]


def case_009(io, question):
    linked = _one(io.llm(f"List only the schema tables and columns needed for the question.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    narrowed = _linked_schema(io.schema, [linked])
    final = io.llm(
        "Use the linked schema subset below, and avoid unrelated tables.\n"
        f"Linked evidence:\n{linked}\nLinked schema:\n{narrowed}\nQuestion:\n{question}"
    )
    return _sql(final)


def case_010(io, question):
    linked_payloads = _many(
        io.llm(
            "Return two independent linked-schema subsets for the question; include table and column names only.",
            n=2,
        )
    )
    narrowed = _linked_schema(io.schema, linked_payloads)
    final = io.llm(
        "Write SQL from the linked subsets and reduced schema. Do not use tables absent from the reduced schema.\n"
        f"Subset 1:\n{linked_payloads[0] if linked_payloads else ''}\n"
        f"Subset 2:\n{linked_payloads[1] if len(linked_payloads) > 1 else ''}\n"
        f"Reduced schema:\n{narrowed}\nQuestion:\n{question}"
    )
    return _sql(final)


def case_011(io, question):
    io.llm(f"Identify relevant schema for this question.\nSchema:\n{io.schema}\nQuestion:\n{question}")
    final = io.llm(f"Write SQL using the full schema.\nSchema:\n{io.schema}\nQuestion:\n{question}")
    return _sql(final)


def case_012(io, question):
    final = io.llm(f"Write SQL. Consider every table in this complete schema.\nSchema:\n{io.schema}\nQuestion:\n{question}")
    return _sql(final)


def case_013(io, question):
    final = io.llm(
        "Write one SQL query. Preserve the original question and schema constraints. "
        "If the question includes a Hint, treat that Hint as an additional explicit requirement outside the original wording.\n"
        f"Schema:\n{io.schema}\nOriginal question:\n{question}"
    )
    return _sql(final)


def case_014(io, question):
    final = io.llm(
        f"Schema:\n{io.schema}\nQuestion:\n{question}",
        system="Return one SQL query. Keep the schema and original question intact, and apply any Hint text as a hard extra constraint.",
        temperature=0.0,
        n=1,
    )
    return _sql(final)


def case_015(io, question):
    final = io.llm(f"{io.schema}\n{question}")
    return _sql(final)


def case_016(io, question):
    final = io.llm(
        "Write SQL for the original question. Ignore any Hint text if one is present.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}"
    )
    return _sql(final)


def case_017(io, question):
    first = _sql(io.llm(f"Write SQL using a join-focused formulation.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    second = _sql(io.llm(f"Write SQL using an aggregation/filter-first formulation.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    first_result = io.execute(first)
    second_result = io.execute(second)
    if isinstance(first_result, dict) and first_result.get("ok") and first_result.get("rows"):
        return first
    if isinstance(second_result, dict) and second_result.get("ok") and second_result.get("rows"):
        return second
    return _first_working([first, second], [first_result, second_result])


def case_018(io, question):
    candidates = [_sql(item) for item in _many(io.llm(f"Produce two semantically different SQL constructions.\nSchema:\n{io.schema}\nQuestion:\n{question}", n=2))]
    while len(candidates) < 2:
        candidates.append(_sql(io.llm(f"Produce another SQL construction.\nSchema:\n{io.schema}\nQuestion:\n{question}")))
    results = [io.execute(candidate) for candidate in candidates[:2]]
    both_usable = all(isinstance(result, dict) and result.get("ok") and result.get("rows") for result in results)
    if both_usable:
        return candidates[0]
    return _first_working(candidates[:2], results)


def case_019(io, question):
    first = _sql(io.llm(f"Write SQL for this question.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    second = first + " "
    io.execute(first)
    io.execute(second)
    return first


def case_020(io, question):
    first = _sql(io.llm(f"Write SQL from one perspective.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    second = _sql(io.llm(f"Write SQL from another perspective.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    io.execute(first)
    io.execute(second)
    return second


def case_021(io, question):
    plan = _json_list(io.llm(f"Return a JSON string list of two steps for solving this SQL task.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    partials = []
    for index, step in enumerate(plan, 1):
        answer = _one(
            io.llm(
                f"Answer step {index} for the SQL task. Use prior partial answers as evidence.\n"
                f"Schema:\n{io.schema}\nQuestion:\n{question}\nStep:\n{step}\nPrior partials:\n{json.dumps(partials)}"
            )
        )
        partials.append({"step": step, "answer": answer})
    final = io.llm(
        "Assemble the final SQL using the partial answers, not just the step names.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nPartial answers:\n{json.dumps(partials, ensure_ascii=True)}"
    )
    return _sql(final)


def case_022(io, question):
    plan = _json_list(io.llm(f"Plan this query as a JSON list of ordered subtasks.\nSchema:\n{io.schema}\nQuestion:\n{question}"))[:2]
    collected = []
    for step in plan:
        collected.append(_one(io.llm(f"Solve this subtask and return the useful intermediate facts.\nSchema:\n{io.schema}\nQuestion:\n{question}\nSubtask:\n{step}\nEarlier facts:\n{json.dumps(collected)}")))
    final = io.llm(
        "Write the final SQL. Incorporate every intermediate fact below.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nIntermediate facts:\n{json.dumps(collected, ensure_ascii=True)}"
    )
    return _sql(final)


def case_023(io, question):
    plan = _json_list(io.llm(f"Return a JSON list plan for this task.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    final = io.llm(f"Write SQL using these step titles only.\nSteps:\n{json.dumps(plan)}\nSchema:\n{io.schema}\nQuestion:\n{question}")
    return _sql(final)


def case_024(io, question):
    plan = _json_list(io.llm(f"Return a JSON list plan for this task.\nSchema:\n{io.schema}\nQuestion:\n{question}"))[:2]
    for step in plan:
        io.llm(f"Work on this subtask.\nSchema:\n{io.schema}\nQuestion:\n{question}\nSubtask:\n{step}")
    final = io.llm(f"Now write SQL from the original problem.\nSchema:\n{io.schema}\nQuestion:\n{question}")
    return _sql(final)


def case_025(io, question):
    first = _sql(io.llm(f"Write SQL for this task.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    result = io.execute(first)
    if isinstance(result, dict) and result.get("ok"):
        return first
    category = _classify_error(result.get("error") if isinstance(result, dict) else result)
    action = {
        "syntax": "fix SQL grammar, parentheses, aliases, and clauses without changing the intended question",
        "schema": "check table and column names against the schema and replace invalid references",
        "semantics": "revise joins, filters, grouping, or aggregation to match the question intent",
    }[category]
    fixed = io.llm(
        f"The execution error is classified as {category}. {action}. Return only SQL.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nPrevious SQL:\n{first}\nError:\n{result}"
    )
    return _sql(fixed)


def case_026(io, question):
    first = _sql(io.llm(f"Draft SQL.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    result = io.execute(first)
    if isinstance(result, dict) and result.get("ok"):
        return first
    category = _one(
        io.llm(
            "Classify the database feedback as exactly one of syntax, schema, or semantics.\n"
            f"Feedback:\n{result}\nSQL:\n{first}"
        )
    ).strip().lower()
    if category not in {"syntax", "schema", "semantics"}:
        category = _classify_error(result.get("error") if isinstance(result, dict) else result)
    prompts = {
        "syntax": "Repair only the SQL syntax and clause ordering.",
        "schema": "Repair invalid table or column references using the provided schema.",
        "semantics": "Repair the query logic so the joins, predicates, and aggregates answer the question.",
    }
    fixed = io.llm(
        f"{prompts[category]} Return only SQL.\nSchema:\n{io.schema}\nQuestion:\n{question}\nSQL:\n{first}\nFeedback:\n{result}"
    )
    return _sql(fixed)


def case_027(io, question):
    first = _sql(io.llm(f"Draft SQL.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    result = io.execute(first)
    if isinstance(result, dict) and result.get("ok"):
        return first
    fixed = io.llm(
        "This might be syntax, schema, or semantics. Try any generic correction and return SQL.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nSQL:\n{first}\nFeedback:\n{result}"
    )
    return _sql(fixed)


def case_028(io, question):
    first = _sql(io.llm(f"Draft SQL.\nSchema:\n{io.schema}\nQuestion:\n{question}"))
    result = io.execute(first)
    if isinstance(result, dict) and result.get("ok"):
        return first
    category = _classify_error(result.get("error") if isinstance(result, dict) else result)
    fixed = io.llm(
        f"The issue category is {category}. Make a minimal generic edit and return SQL.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nSQL:\n{first}\nFeedback:\n{result}"
    )
    return _sql(fixed)


def case_029(io, question):
    final = io.llm(
        "Return the answer as a single SQL code fence with no explanation or extra text.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}"
    )
    return _sql(final)


def case_030(io, question):
    final = io.llm(
        f"Schema:\n{io.schema}\nQuestion:\n{question}",
        system="You must answer with exactly one fenced SQL block and nothing outside the fence.",
        temperature=0.0,
        n=1,
    )
    return _sql(final)


def case_031(io, question):
    final = io.llm(f"Schema:\n{io.schema}\nQuestion:\n{question}")
    return _sql(final)


def case_032(io, question):
    final = io.llm(
        "Do not use a SQL code fence. Explain briefly before the query.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}"
    )
    return _sql(final)


CASES = [
    {"case_id": "ic001", "strategy": "repair", "solve": case_001},
    {"case_id": "ic002", "strategy": "repair", "solve": case_002},
    {"case_id": "ic003", "strategy": "repair", "solve": case_003},
    {"case_id": "ic004", "strategy": "repair", "solve": case_004},
    {"case_id": "ic005", "strategy": "vote3", "solve": case_005},
    {"case_id": "ic006", "strategy": "vote3", "solve": case_006},
    {"case_id": "ic007", "strategy": "vote3", "solve": case_007},
    {"case_id": "ic008", "strategy": "vote3", "solve": case_008},
    {"case_id": "ic009", "strategy": "schema_link", "solve": case_009},
    {"case_id": "ic010", "strategy": "schema_link", "solve": case_010},
    {"case_id": "ic011", "strategy": "schema_link", "solve": case_011},
    {"case_id": "ic012", "strategy": "schema_link", "solve": case_012},
    {"case_id": "ic013", "strategy": "hint_guard", "solve": case_013},
    {"case_id": "ic014", "strategy": "hint_guard", "solve": case_014},
    {"case_id": "ic015", "strategy": "hint_guard", "solve": case_015},
    {"case_id": "ic016", "strategy": "hint_guard", "solve": case_016},
    {"case_id": "ic017", "strategy": "two_view", "solve": case_017},
    {"case_id": "ic018", "strategy": "two_view", "solve": case_018},
    {"case_id": "ic019", "strategy": "two_view", "solve": case_019},
    {"case_id": "ic020", "strategy": "two_view", "solve": case_020},
    {"case_id": "ic021", "strategy": "decompose", "solve": case_021},
    {"case_id": "ic022", "strategy": "decompose", "solve": case_022},
    {"case_id": "ic023", "strategy": "decompose", "solve": case_023},
    {"case_id": "ic024", "strategy": "decompose", "solve": case_024},
    {"case_id": "ic025", "strategy": "error_classify", "solve": case_025},
    {"case_id": "ic026", "strategy": "error_classify", "solve": case_026},
    {"case_id": "ic027", "strategy": "error_classify", "solve": case_027},
    {"case_id": "ic028", "strategy": "error_classify", "solve": case_028},
    {"case_id": "ic029", "strategy": "format_guard", "solve": case_029},
    {"case_id": "ic030", "strategy": "format_guard", "solve": case_030},
    {"case_id": "ic031", "strategy": "format_guard", "solve": case_031},
    {"case_id": "ic032", "strategy": "format_guard", "solve": case_032},
]
