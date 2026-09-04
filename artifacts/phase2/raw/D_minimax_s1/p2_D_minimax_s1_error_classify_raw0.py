"""P2P2D Error-Classification Harness that classifies execution failures into syntax / schema / semantics and applies targeted fixes up to 2 rounds."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are an expert Text-to-SQL generator. "
    "Given a natural language question and a database schema, "
    "produce exactly one syntactically valid SQL query. "
    "Output ONLY the SQL query and nothing else."
)

GEN_PROMPT = (
    "Schema:\n{schema}\n\n"
    "Question: {question}\n\n"
    "Write a single SQL query that answers the question. "
    "Return ONLY the SQL."
)

FIX_SYNTAX_PROMPT = (
    "Your previous SQL had a SYNTAX error. "
    "The database returned this error:\n"
    "{error}\n\n"
    "Original SQL:\n{sql}\n\n"
    "Schema:\n{schema}\n\n"
    "Question: {question}\n\n"
    "Fix the SQL and return ONLY the corrected SQL."
)

FIX_SCHEMA_PROMPT = (
    "Your previous SQL had a SCHEMA error (wrong column, table, or ambiguous reference). "
    "The database returned this error:\n"
    "{error}\n\n"
    "Original SQL:\n{sql}\n\n"
    "Schema:\n{schema}\n\n"
    "Question: {question}\n\n"
    "Re-examine the schema carefully. Make sure every table and column you reference "
    "actually exists in the schema and that you do not use ambiguous references. "
    "Return ONLY the corrected SQL."
)

FIX_SEMANTIC_PROMPT = (
    "Your previous SQL was SYNTACTICALLY VALID and referenced the correct tables/columns, "
    "but it produced results that do not match the intent of the question. "
    "The execution error (if any) was:\n"
    "{error}\n\n"
    "Original SQL:\n{sql}\n\n"
    "Schema:\n{schema}\n\n"
    "Question: {question}\n\n"
    "Reconsider the SEMANTICS of the question (filters, joins, aggregations, grouping, ordering). "
    "Return ONLY a corrected SQL that better matches the question's intent."
)


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------

_SYNTAX_PATTERNS = [
    r"syntax error",
    r"near \"",
    r"unexpected token",
    r"parse error",
    r"unterminated",
    r"unmatched parenthesis",
    r"mismatched input",
    r"you have an error in your sql syntax",
    r"end of input",
    r"sql syntax",
    r"\bORA-00\d{3}\b",          # ORA-00900..00999 generally syntax/parse
    r"\bORA-020\d{2}\b",          # ORA-020xx often runtime but covered broadly
]

_SCHEMA_PATTERNS = [
    r"no such (table|column|function|relation)",
    r"unknown column",
    r"unknown table",
    r"table .* doesn't exist",
    r"column .* does not exist",
    r"relation .* does not exist",
    r"ambiguous column",
    r"ambiguous reference",
    r"column reference .* is ambiguous",
    r"table or view not found",
    r"object .* does not exist",
    r"invalid identifier",
    r"undefined column",
    r"undefined table",
    r"missing from-clause entry",
    r"\bORA-00904\b",             # invalid identifier
    r"\bORA-00942\b",             # table or view does not exist
    r"\bORA-02289\b",             # sequence does not exist
]

_SEMANTIC_PATTERNS = [
    r"division by zero",
    r"out of range",
    r"datatype mismatch",
    r"type mismatch",
    r"invalid number",
    r"not a valid month",
    r"not a valid date",
    r"cannot convert",
    r"subquery returned more than",
    r"more than one row",
    r"no rows? returned",
    r"group by",
    r"not in a group by",
    r"must appear in the group by",
    r"not enough arguments",
    r"too many arguments",
    r"function .* does not exist",
    r"window function",
    r"constraint",
    r"foreign key",
    r"primary key",
    r"unique constraint",
    r"not null constraint",
    r"cannot insert",
    r"cannot update",
    r"cannot delete",
    r"\bORA-01436\b",             # recursive with needs connect by
    r"\bORA-01722\b",             # invalid number
    r"\bORA-01830\b",             # date format picture ends before converting entire input string
    r"\bORA-01841\b",             # full year must be between -4713 and +9999
    r"\bORA-01843\b",             # not a valid month
    r"\bORA-01861\b",             # literal does not match format string
    r"\bORA-02290\b",             # check constraint violated
    r"\bORA-02291\b",             # integrity constraint violated - parent key not found
    r"\bORA-02292\b",             # integrity constraint violated - child record found
    r"\bORA-04091\b",             # table is mutating
    r"division by zero",
]


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_SYNTAX_RE = _compile(_SYNTAX_PATTERNS)
_SCHEMA_RE = _compile(_SCHEMA_PATTERNS)
_SEMANTIC_RE = _compile(_SEMANTIC_PATTERNS)


def _classify_error(error: str) -> str:
    """Classify an execution error string.

    Returns one of: "syntax", "schema", "semantic".
    A "semantic" classification here means "not clearly syntax/schema" --
    it covers runtime / logical / type errors.
    """
    if not error:
        return "semantic"

    # Schema errors take priority over generic syntax ones because many
    # database engines report missing identifiers as a parse/syntax error.
    for p in _SCHEMA_RE:
        if p.search(error):
            return "schema"
    for p in _SYNTAX_RE:
        if p.search(error):
            return "syntax"
    for p in _SEMANTIC_RE:
        if p.search(error):
            return "semantic"

    # Fallback heuristic: short errors with tokens common in parse errors
    # are treated as syntax, everything else as semantic.
    low = error.lower()
    if any(tok in low for tok in ("syntax", "parse", "token", "unexpected", "expected")):
        return "syntax"
    if any(tok in low for tok in ("does not exist", "not found", "unknown", "invalid identifier")):
        return "schema"
    return "semantic"


# ---------------------------------------------------------------------------
# SQL extraction helper (delegates to bridge.extract_sql, with a defensive
# fallback that finds the first SELECT/WITH/INSERT/UPDATE/DELETE).
# ---------------------------------------------------------------------------

_FALLBACK_SQL_RE = re.compile(
    r"(?:SELECT|WITH|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b.*?(?:;|$)",
    re.IGNORECASE | re.DOTALL,
)


def _extract_sql(text: str) -> str:
    sql = ""
    try:
        sql = bridge.extract_sql(text) or ""
    except Exception:
        sql = ""
    if sql and sql.strip():
        return sql.strip().rstrip(";").strip()
    m = _FALLBACK_SQL_RE.search(text or "")
    if m:
        return m.group(0).strip().rstrip(";").strip()
    return (text or "").strip().rstrip(";").strip()


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class P2P2DMinimaxS1ErrorClassify(SQLHarness):
    """P2P2D Error-Classification harness.

    Pipeline:
      1. Generate SQL with the frozen weak solver.
      2. Execute it.
      3. If it fails, classify the failure into one of three classes:
         - syntax  : the SQL string itself is malformed
         - schema  : identifiers (table/column) are wrong or ambiguous
         - semantic: SQL runs but the meaning / types are wrong
      4. Apply a class-specific fix prompt and retry, up to 2 rounds total.
      5. Return the first SQL that executes successfully; otherwise return the
         latest attempt so the harness always returns a string.
    """

    NAME = "P2P2DMinimaxS1ErrorClassify"
    MAX_REPAIRS = 2

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""

        sql = self._generate(question, schema, attempt=0)
        ok, err = self._try_execute(sql)

        last_sql = sql
        rounds = 0

        while not ok and rounds < self.MAX_REPAIRS:
            rounds += 1
            failure_class = _classify_error(err)
            sql = self._repair(question, schema, last_sql, err, failure_class, rounds)
            last_sql = sql
            ok, err = self._try_execute(sql)

        return last_sql

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #
    def _generate(self, question: str, schema: str, attempt: int) -> str:
        prompt = GEN_PROMPT.format(schema=schema, question=question)
        try:
            text = self.llm(prompt, system=SYSTEM_PROMPT, temperature=0.0, n=1)
        except TypeError:
            # Some harnesses expose llm differently.
            text = self.llm(prompt)
        if not isinstance(text, str):
            text = str(text)
        return _extract_sql(text)

    def _repair(
        self,
        question: str,
        schema: str,
        sql: str,
        error: str,
        failure_class: str,
        attempt: int,
    ) -> str:
        if failure_class == "syntax":
            prompt = FIX_SYNTAX_PROMPT.format(
                schema=schema, question=question, sql=sql, error=error
            )
            system = SYSTEM_PROMPT
            # Allow slightly higher temperature to escape repeated parse mistakes.
            temperature = 0.2 if attempt >= 1 else 0.0
        elif failure_class == "schema":
            prompt = FIX_SCHEMA_PROMPT.format(
                schema=schema, question=question, sql=sql, error=error
            )
            system = SYSTEM_PROMPT + " Pay close attention to the exact table and column names in the schema."
            temperature = 0.0
        else:  # semantic
            prompt = FIX_SEMANTIC_PROMPT.format(
                schema=schema, question=question, sql=sql, error=error
            )
            system = (
                SYSTEM_PROMPT
                + " Focus on the logical meaning of the question: filters, joins, "
                "aggregations, grouping, and ordering."
            )
            # A bit of stochasticity helps the weak solver find a different logic.
            temperature = 0.3 if attempt >= 1 else 0.1

        try:
            text = self.llm(prompt, system=system, temperature=temperature, n=1)
        except TypeError:
            text = self.llm(prompt)

        if not isinstance(text, str):
            text = str(text)

        new_sql = _extract_sql(text)
        # Defensive: if the model returned empty, keep the previous attempt.
        return new_sql if new_sql else sql

    def _try_execute(self, sql: str) -> Tuple[bool, str]:
        if not sql or not sql.strip():
            return False, "empty sql"

        try:
            result: Dict[str, Any] = self.execute(sql)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - defensive
            return False, f"execution exception: {exc}"

        ok = bool(result.get("ok", False))
        if ok:
            return True, ""

        err = result.get("error") or result.get("message") or ""
        if not isinstance(err, str):
            err = str(err)
        return False, err