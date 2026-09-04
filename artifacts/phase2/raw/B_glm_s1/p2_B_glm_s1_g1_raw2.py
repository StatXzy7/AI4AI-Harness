"""Repair-loop harness: generate SQL, execute it, and feed the exact database error back to the solver for up to two corrective regenerations."""
# MECHANISM: repair

import re

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2BGlmS1G1"]


class P2P2BGlmS1G1(SQLHarness):
    """Text-to-SQL with execution-feedback repair.

    Instead of a single greedy call, the harness runs a
    generate -> execute -> repair loop:

    1. Ask the frozen solver for one read-only SELECT statement.
    2. Run it against the database via ``self.execute``.
    3. If execution fails (or nothing was extracted, or the statement is
       not a read-only SELECT), build a repair prompt containing the
       failing SQL and the exact SQLite error message and ask the solver
       to fix it.
    4. Stop after ``MAX_REPAIRS`` corrective rounds, or as soon as a query
       both executes cleanly and references the schema.

    The best candidate ever seen is returned: queries that execute
    outrank queries that do not; among equals, the schema-relevant and
    then the earliest one wins, so a bad repair never discards a working
    earlier attempt.
    """

    MAX_REPAIRS = 2        # corrective rounds after the first attempt
    MAX_ERROR_CHARS = 300  # truncate error text fed back to the model
    MAX_SQL_CHARS = 2000   # truncate SQL echoed back in repair prompts
    MAX_HISTORY = 3        # failed attempts echoed in repair prompts

    _SYSTEM = (
        "You are an expert SQLite analyst. Translate the question into "
        "exactly one read-only SQLite SELECT statement. Output only the "
        "SQL, with no explanation."
    )

    _WRITE_RE = re.compile(
        r"^\s*(insert|update|delete|drop|alter|create|replace|truncate|"
        r"attach|detach|grant|revoke|vacuum|reindex|pragma)\b",
        re.IGNORECASE,
    )

    _KEYWORDS = frozenset("""
        select from where group order by having limit offset join inner
        left right outer full cross on as and or not in is null like
        ilike between exists case when then else end distinct union all
        intersect except asc desc count sum avg min max total
        group_concat cast integer int text real numeric blob varchar char
        date time datetime timestamp boolean values insert into update
        set delete create table primary key foreign references index
        unique default check constraint autoincrement with recursive
        using natural if nulls first last filter over partition rows
        range preceding following current row unbounded glob regexp match
        escape collate nocase true false strftime julianday now substr
        length upper lower trim coalesce ifnull nullif quote hex random
        abs round typeof instr printf format
    """.split())

    # ------------------------------------------------------------------ #
    # main control flow
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        prompt = self._initial_prompt(question)
        failures = []            # [(sql, error), ...] in attempt order
        best_sql = ""
        best_score = -1

        for attempt in range(self.MAX_REPAIRS + 1):
            sql = self._generate(prompt)
            ok, error = self._run(sql)
            relevant = self._references_schema(sql)

            score = (2 if ok else 0) + (1 if relevant else 0)
            if sql and score > best_score:
                best_score, best_sql = score, sql

            failures.append((sql, error))
            if ok and relevant:
                return sql                      # nothing left to repair
            if attempt < self.MAX_REPAIRS:
                prompt = self._repair_prompt(question, failures)

        return best_sql

    # ------------------------------------------------------------------ #
    # helpers: generation, execution, validation
    # ------------------------------------------------------------------ #
    def _generate(self, prompt: str) -> str:
        """One call to the frozen solver, reduced to a bare SQL string."""
        try:
            text = self.llm(prompt, system=self._SYSTEM, temperature=0.0, n=1)
        except Exception:
            return ""
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            return ""
        if not sql:
            return ""
        sql = sql.strip()
        sql = re.sub(r";\s*$", "", sql).strip()
        return sql

    def _run(self, sql: str):
        """Execute a candidate; return (ok, error_message)."""
        if not sql:
            return False, "No SQL statement was found in the output."
        match = self._WRITE_RE.match(sql)
        if match:
            return False, (
                "'%s' statements are not allowed; answer with a single "
                "read-only SELECT query." % match.group(1).lower()
            )
        try:
            result = self.execute(sql)
        except Exception as exc:
            return False, "Executor raised an exception: %s" % exc
        if not isinstance(result, dict):
            return False, "Executor returned an unexpected result type."
        if result.get("ok"):
            return True, ""
        error = result.get("error") or "execution failed"
        return False, str(error)[: self.MAX_ERROR_CHARS]

    def _references_schema(self, sql: str) -> bool:
        """Heuristic: does the query mention any identifier from the schema?"""
        schema = getattr(self, "schema", None) or ""
        if not sql or not schema.strip():
            return True
        sql_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", sql.lower()))
        sql_ids -= self._KEYWORDS
        if not sql_ids:
            return False
        schema_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", schema.lower()))
        return bool(sql_ids & schema_ids)

    # ------------------------------------------------------------------ #
    # helpers: prompts
    # ------------------------------------------------------------------ #
    def _initial_prompt(self, question: str) -> str:
        return "\n".join([
            "Database schema:",
            self._schema_text(),
            "",
            "Question: %s" % question.strip(),
            "",
            "Write one SQLite SELECT statement that answers this question "
            "using only the tables and columns in the schema. Output only "
            "the SQL statement.",
        ])

    def _repair_prompt(self, question: str, failures) -> str:
        lines = [
            "Database schema:",
            self._schema_text(),
            "",
            "Question: %s" % question.strip(),
            "",
            "Your previous SQL attempts against this database failed. "
            "Here is what happened:",
        ]
        recent = failures[-self.MAX_HISTORY:]
        base = len(failures) - len(recent)
        for i, (sql, error) in enumerate(recent, start=base + 1):
            lines.append("")
            lines.append("Attempt %d SQL:" % i)
            lines.append(self._truncate(sql, self.MAX_SQL_CHARS)
                         or "(no SQL extracted)")
            lines.append("SQLite error: %s" % (
                self._truncate(error, self.MAX_ERROR_CHARS)
                or "unknown error"))
        lines.append("")
        lines.append(
            "Rewrite the query so it runs without error and answers the "
            "question. Use only tables and columns that appear in the "
            "schema, and output only a single read-only SQLite SELECT "
            "statement."
        )
        return "\n".join(lines)

    def _schema_text(self) -> str:
        return (getattr(self, "schema", None) or "").strip() \
            or "(no schema provided)"

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        text = (text or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit] + " ...[truncated]"