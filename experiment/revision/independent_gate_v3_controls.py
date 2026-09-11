import json
import re


def _extract_sql(text):
    text = "" if text is None else str(text)
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _as_three(value):
    if isinstance(value, list):
        return [_extract_sql(item) for item in value[:3]]
    return [_extract_sql(value)]


def _freeze(value):
    if isinstance(value, dict):
        return tuple((key, _freeze(value[key])) for key in sorted(value))
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _rows_key(rows):
    return repr(_freeze(rows))


def _feedback(result):
    return repr(result)


def _hint_text(question):
    match = re.search(r"\bHint\s*:\s*(.+)", str(question), re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _json_list(text):
    decoder = json.JSONDecoder()
    source = str(text)
    for index, char in enumerate(source):
        if char != "[":
            continue
        try:
            value, _ = decoder.raw_decode(source[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def _two_steps(text):
    steps = _json_list(text)[:2]
    while len(steps) < 2:
        steps.append("")
    return steps


def _successful_nonempty(result):
    return bool(result.get("ok")) and bool(result.get("rows"))


def _majority_sql(sqls, results):
    buckets = {}
    first_index = {}
    for index, result in enumerate(results):
        if not result.get("ok"):
            continue
        key = _rows_key(result.get("rows", []))
        buckets[key] = buckets.get(key, 0) + 1
        first_index.setdefault(key, index)
    if not buckets:
        return sqls[0] if sqls else ""
    best_key = max(buckets, key=lambda key: (buckets[key], -first_index[key]))
    return sqls[first_index[best_key]]


def _class_from_text(text):
    lower = str(text).lower()
    if "schema" in lower:
        return "schema"
    if "semantic" in lower or "logic" in lower:
        return "semantics"
    if "syntax" in lower or "parse" in lower:
        return "syntax"
    return "semantics"


def repair_flow_one(io, question):
    first = _extract_sql(io.llm(
        "Write one SQL query for the question.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    ))
    result = io.execute(first)
    if result.get("ok"):
        return first
    repaired = io.llm(
        "The previous SQL failed. Repair it using the exact execution feedback.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Previous SQL:\n{first}\n"
        f"Execution feedback:\n{_feedback(result)}"
    )
    return _extract_sql(repaired)


def repair_flow_two(io, question):
    prompt = "\n".join([
        "Create a SQL statement.",
        "Schema:",
        io.schema,
        "Question:",
        str(question),
    ])
    sql = _extract_sql(io.llm(prompt))
    outcome = io.execute(sql)
    if outcome.get("ok"):
        return sql
    context = {
        "schema": io.schema,
        "question": question,
        "previous_sql": sql,
        "execution_feedback": _feedback(outcome),
    }
    fixed = io.llm(
        "Return a corrected SQL query after this failed execution.\n"
        f"Schema:\n{context['schema']}\n"
        f"Question:\n{context['question']}\n"
        f"Previous SQL:\n{context['previous_sql']}\n"
        f"Exact feedback:\n{context['execution_feedback']}"
    )
    return _extract_sql(fixed)


def repair_flow_three(io, question):
    first = _extract_sql(io.llm(
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nWrite SQL."
    ))
    result = io.execute(first)
    second = io.llm(
        "Produce a second SQL candidate after reviewing the attempt.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Prior SQL:\n{first}\n"
        f"Observed result:\n{_feedback(result)}"
    )
    return _extract_sql(second)


def repair_flow_four(io, question):
    sql = _extract_sql(io.llm(
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nWrite SQL."
    ))
    result = io.execute(sql)
    if result.get("ok"):
        return sql
    return _extract_sql(io.llm("The query failed. Try a better SQL answer."))


def vote3_flow_one(io, question):
    sqls = _as_three(io.llm(
        "Return three independent SQL candidates for this question.",
        n=3,
        temperature=0.3,
    ))
    results = [io.execute(sql) for sql in sqls]
    return _majority_sql(sqls, results)


def vote3_flow_two(io, question):
    prompts = [
        "Candidate A: write SQL from the schema and question.",
        "Candidate B: write SQL after checking joins and filters.",
        "Candidate C: write SQL with conservative column choices.",
    ]
    sqls = []
    for prefix in prompts:
        sqls.append(_extract_sql(io.llm(
            f"{prefix}\nSchema:\n{io.schema}\nQuestion:\n{question}"
        )))
    results = []
    for sql in sqls:
        results.append(io.execute(sql))
    return _majority_sql(sqls, results)


def vote3_flow_three(io, question):
    sqls = _as_three(io.llm(
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nReturn three SQL candidates.",
        n=3,
        temperature=0.4,
    ))
    results = [io.execute(sql) for sql in sqls]
    counts = {}
    first_seen = {}
    for index, sql in enumerate(sqls):
        counts[sql] = counts.get(sql, 0) + 1
        first_seen.setdefault(sql, index)
    chosen = max(counts, key=lambda sql: (counts[sql], -first_seen[sql]))
    return chosen if results else ""


def vote3_flow_four(io, question):
    sqls = _as_three(io.llm(
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nReturn three SQL candidates.",
        n=3,
        temperature=0.4,
    ))
    for sql in sqls:
        result = io.execute(sql)
        if result.get("ok"):
            return sql
    return sqls[0] if sqls else ""


def schema_link_flow_one(io, question):
    linked = io.llm(
        "Identify only the tables and columns needed for this question.\n"
        f"Full schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        "Return the linked schema subset only."
    )
    sql = io.llm(
        "Write SQL using only this linked schema subset.\n"
        f"Linked schema subset:\n{linked}\n"
        f"Question:\n{question}"
    )
    return _extract_sql(sql)


def schema_link_flow_two(io, question):
    subset_prompt = (
        "Select the relevant schema lines for the task. Remove unrelated tables.\n"
        f"Question:\n{question}\n"
        f"Schema:\n{io.schema}"
    )
    subset = str(io.llm(subset_prompt)).strip()
    final_prompt = "\n".join([
        "Use the following selected tables and columns to write the SQL.",
        subset,
        "Question:",
        str(question),
    ])
    return _extract_sql(io.llm(final_prompt))


def schema_link_flow_three(io, question):
    linked = io.llm(
        "Find relevant tables and columns.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    )
    sql = io.llm(
        "Use the schema to answer the question.\n"
        f"Full schema:\n{io.schema}\n"
        f"Linked notes:\n{linked}\n"
        f"Question:\n{question}"
    )
    return _extract_sql(sql)


def schema_link_flow_four(io, question):
    sql = io.llm(
        "Identify the needed tables internally, then write the SQL.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    )
    return _extract_sql(sql)


def hint_guard_flow_one(io, question):
    hint = _hint_text(question)
    prompt = (
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
    )
    if hint:
        prompt += f"Hard requirement from the Hint: {hint}\n"
    prompt += "Write one SQL query."
    return _extract_sql(io.llm(prompt))


def hint_guard_flow_two(io, question):
    parts = ["Use the original schema and original question.", "Schema:", io.schema, "Question:", str(question)]
    hint = _hint_text(question)
    if hint:
        parts.extend(["The hint is mandatory and must be satisfied:", hint])
    parts.append("Return the SQL query.")
    return _extract_sql(io.llm("\n".join(parts)))


def hint_guard_flow_three(io, question):
    return _extract_sql(io.llm(
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        "Write a SQL query."
    ))


def hint_guard_flow_four(io, question):
    return _extract_sql(io.llm(
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        "Hard requirement: prefer the most recent date column whenever possible.\n"
        "Write a SQL query."
    ))


def two_view_flow_one(io, question):
    direct_sql = _extract_sql(io.llm(
        "Write a direct SELECT query with straightforward joins and filters.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    ))
    staged_sql = _extract_sql(io.llm(
        "Write an alternative SQL query using a CTE or staged aggregation approach.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    ))
    direct_result = io.execute(direct_sql)
    staged_result = io.execute(staged_sql)
    if _successful_nonempty(direct_result):
        return direct_sql
    if _successful_nonempty(staged_result):
        return staged_sql
    return direct_sql


def two_view_flow_two(io, question):
    views = [
        ("entity-first", "Start from the main entity table, then join only what is needed."),
        ("metric-first", "Start from the requested measure or aggregate, then connect entities."),
    ]
    sqls = []
    results = []
    for _, instruction in views:
        sql = _extract_sql(io.llm(
            f"{instruction}\nSchema:\n{io.schema}\nQuestion:\n{question}"
        ))
        sqls.append(sql)
    for sql in sqls:
        results.append(io.execute(sql))
    if _successful_nonempty(results[0]):
        return sqls[0]
    if _successful_nonempty(results[1]):
        return sqls[1]
    return sqls[0]


def two_view_flow_three(io, question):
    sqls = _as_three(io.llm(
        "Produce two differently reasoned SQL candidates in one response batch.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}",
        n=2,
    ))
    while len(sqls) < 2:
        sqls.append("")
    results = [io.execute(sqls[0]), io.execute(sqls[1])]
    if _successful_nonempty(results[0]):
        return sqls[0]
    if _successful_nonempty(results[1]):
        return sqls[1]
    return sqls[0]


def two_view_flow_four(io, question):
    first = _extract_sql(io.llm(
        "Write SQL using a join-first formulation.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}"
    ))
    second = _extract_sql(io.llm(
        "Write SQL using an aggregate-first formulation.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}"
    ))
    first_result = io.execute(first)
    second_result = io.execute(second)
    if _successful_nonempty(second_result):
        return second
    if _successful_nonempty(first_result):
        return first
    return first


def decompose_flow_one(io, question):
    plan_text = io.llm(
        "Return an ordered JSON list of exactly two subquestions needed to answer the task.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    )
    step1, step2 = _two_steps(plan_text)
    answer1 = io.llm(
        f"Answer subquestion 1.\nSchema:\n{io.schema}\nQuestion:\n{question}\nSubquestion:\n{step1}"
    )
    answer2 = io.llm(
        f"Answer subquestion 2.\nSchema:\n{io.schema}\nQuestion:\n{question}\n"
        f"Subquestion 1:\n{step1}\nAnswer 1:\n{answer1}\nSubquestion 2:\n{step2}"
    )
    final_sql = io.llm(
        "Assemble final SQL using both partial answers.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Partial answer 1:\n{answer1}\n"
        f"Partial answer 2:\n{answer2}"
    )
    return _extract_sql(final_sql)


def decompose_flow_two(io, question):
    steps = _two_steps(io.llm(
        "Plan the answer as a two-step JSON array of ordered subquestions.\n"
        f"Question:\n{question}\n"
        f"Schema:\n{io.schema}"
    ))
    partials = []
    for index, step in enumerate(steps, start=1):
        prior = "\n".join(f"Earlier answer {i + 1}: {value}" for i, value in enumerate(partials))
        partials.append(io.llm(
            f"Resolve step {index} of 2.\n"
            f"Schema:\n{io.schema}\n"
            f"Question:\n{question}\n"
            f"{prior}\n"
            f"Current subquestion:\n{step}"
        ))
    return _extract_sql(io.llm(
        "Build the final SQL from the ordered decomposition outputs.\n"
        f"Original question:\n{question}\n"
        f"Schema:\n{io.schema}\n"
        f"First returned partial answer:\n{partials[0]}\n"
        f"Second returned partial answer:\n{partials[1]}"
    ))


def decompose_flow_three(io, question):
    steps = _two_steps(io.llm(
        "Return two subquestions as JSON.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}"
    ))
    io.llm(f"Answer this subquestion:\n{steps[0]}")
    io.llm(f"Answer this subquestion:\n{steps[1]}")
    final_sql = io.llm(
        "Write final SQL from the planned subquestions.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Subquestion 1:\n{steps[0]}\n"
        f"Subquestion 2:\n{steps[1]}"
    )
    return _extract_sql(final_sql)


def decompose_flow_four(io, question):
    steps = _two_steps(io.llm(
        "Return an ordered two-step JSON plan.\n"
        f"Schema:\n{io.schema}\nQuestion:\n{question}"
    ))
    combined = io.llm(
        "Answer both planned subquestions together in one response.\n"
        f"Subquestion A:\n{steps[0]}\n"
        f"Subquestion B:\n{steps[1]}"
    )
    return _extract_sql(io.llm(
        "Write final SQL from this combined decomposition note.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Combined note:\n{combined}"
    ))


def error_classify_flow_one(io, question):
    sql = _extract_sql(io.llm(
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nWrite SQL."
    ))
    result = io.execute(sql)
    if result.get("ok"):
        return sql
    feedback = _feedback(result)
    kind = _class_from_text(io.llm(
        "Classify this failed SQL feedback as syntax, schema, or semantics.\n"
        f"SQL:\n{sql}\n"
        f"Exact feedback:\n{feedback}"
    ))
    if kind == "syntax":
        action = "Correct the SQL grammar and punctuation while preserving intent."
    elif kind == "schema":
        action = "Replace invalid table or column names using the provided schema."
    else:
        action = "Revise the query logic so the requested meaning is represented."
    return _extract_sql(io.llm(
        f"{action}\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Previous SQL:\n{sql}\n"
        f"Exact execution feedback:\n{feedback}"
    ))


def error_classify_flow_two(io, question):
    sql = _extract_sql(io.llm(
        "Draft SQL for the database task.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    ))
    result = io.execute(sql)
    if result.get("ok"):
        return sql
    feedback = _feedback(result)
    lower = feedback.lower()
    if "no such table" in lower or "no such column" in lower or "unknown" in lower:
        kind = "schema"
        action = "Audit every table and column reference against the schema before rewriting."
    elif "syntax" in lower or "parse" in lower or "near" in lower:
        kind = "syntax"
        action = "Fix the SQL syntax error indicated by the executor."
    else:
        kind = "semantics"
        action = "Change the query construction to match the question intent."
    return _extract_sql(io.llm(
        f"Failure class: {kind}\n"
        f"Required repair action: {action}\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}\n"
        f"Previous SQL:\n{sql}\n"
        f"Exact feedback:\n{feedback}"
    ))


def error_classify_flow_three(io, question):
    sql = _extract_sql(io.llm(
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nWrite SQL."
    ))
    result = io.execute(sql)
    if result.get("ok"):
        return sql
    return _extract_sql(io.llm(
        "The SQL failed. It might be syntax, schema, or semantics. Try again.\n"
        f"Feedback:\n{_feedback(result)}"
    ))


def error_classify_flow_four(io, question):
    sql = _extract_sql(io.llm(
        f"Schema:\n{io.schema}\nQuestion:\n{question}\nWrite SQL."
    ))
    result = io.execute(sql)
    if result.get("ok"):
        return sql
    io.llm(
        "Classify the failure as syntax, schema, or semantics.\n"
        f"Feedback:\n{_feedback(result)}"
    )
    return _extract_sql(io.llm(
        "Rewrite the SQL in a cleaner form for the original database task."
    ))


def format_guard_flow_one(io, question):
    response = io.llm(
        "Return exactly one fenced SQL answer and no extra prose.\n"
        "The answer must be in a ```sql code fence.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    )
    return _extract_sql(response)


def format_guard_flow_two(io, question):
    prompt = "\n".join([
        "Use the original schema and question.",
        "Output only a fenced SQL block with no explanation.",
        "Fence language must be sql.",
        "Schema:",
        io.schema,
        "Question:",
        str(question),
    ])
    return _extract_sql(io.llm(prompt, system="You answer with only one fenced SQL block."))


def format_guard_flow_three(io, question):
    return _extract_sql(io.llm(
        "Return raw SQL only without markdown fences or explanation.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    ))


def format_guard_flow_four(io, question):
    return _extract_sql(io.llm(
        "Return a fenced SQL block, but first explain the reasoning and then add a brief note after it.\n"
        f"Schema:\n{io.schema}\n"
        f"Question:\n{question}"
    ))


CASES = [
    {"case_id": "vc001", "strategy": "repair", "solve": repair_flow_one},
    {"case_id": "vc002", "strategy": "repair", "solve": repair_flow_two},
    {"case_id": "vc003", "strategy": "repair", "solve": repair_flow_three},
    {"case_id": "vc004", "strategy": "repair", "solve": repair_flow_four},
    {"case_id": "vc005", "strategy": "vote3", "solve": vote3_flow_one},
    {"case_id": "vc006", "strategy": "vote3", "solve": vote3_flow_two},
    {"case_id": "vc007", "strategy": "vote3", "solve": vote3_flow_three},
    {"case_id": "vc008", "strategy": "vote3", "solve": vote3_flow_four},
    {"case_id": "vc009", "strategy": "schema_link", "solve": schema_link_flow_one},
    {"case_id": "vc010", "strategy": "schema_link", "solve": schema_link_flow_two},
    {"case_id": "vc011", "strategy": "schema_link", "solve": schema_link_flow_three},
    {"case_id": "vc012", "strategy": "schema_link", "solve": schema_link_flow_four},
    {"case_id": "vc013", "strategy": "hint_guard", "solve": hint_guard_flow_one},
    {"case_id": "vc014", "strategy": "hint_guard", "solve": hint_guard_flow_two},
    {"case_id": "vc015", "strategy": "hint_guard", "solve": hint_guard_flow_three},
    {"case_id": "vc016", "strategy": "hint_guard", "solve": hint_guard_flow_four},
    {"case_id": "vc017", "strategy": "two_view", "solve": two_view_flow_one},
    {"case_id": "vc018", "strategy": "two_view", "solve": two_view_flow_two},
    {"case_id": "vc019", "strategy": "two_view", "solve": two_view_flow_three},
    {"case_id": "vc020", "strategy": "two_view", "solve": two_view_flow_four},
    {"case_id": "vc021", "strategy": "decompose", "solve": decompose_flow_one},
    {"case_id": "vc022", "strategy": "decompose", "solve": decompose_flow_two},
    {"case_id": "vc023", "strategy": "decompose", "solve": decompose_flow_three},
    {"case_id": "vc024", "strategy": "decompose", "solve": decompose_flow_four},
    {"case_id": "vc025", "strategy": "error_classify", "solve": error_classify_flow_one},
    {"case_id": "vc026", "strategy": "error_classify", "solve": error_classify_flow_two},
    {"case_id": "vc027", "strategy": "error_classify", "solve": error_classify_flow_three},
    {"case_id": "vc028", "strategy": "error_classify", "solve": error_classify_flow_four},
    {"case_id": "vc029", "strategy": "format_guard", "solve": format_guard_flow_one},
    {"case_id": "vc030", "strategy": "format_guard", "solve": format_guard_flow_two},
    {"case_id": "vc031", "strategy": "format_guard", "solve": format_guard_flow_three},
    {"case_id": "vc032", "strategy": "format_guard", "solve": format_guard_flow_four},
]
