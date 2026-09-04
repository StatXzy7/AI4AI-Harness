"""Repair-loop harness: greedy SQL generation followed by execute-verification, where any database error and the offending query are fed back to the frozen solver for up to four corrective regeneration rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G5(SQLHarness):
    """Execute-verified repair loop around the frozen weak solver.

    Control flow (a real change over a single greedy call):

    1. One greedy LLM call turns (schema, question) into a candidate query.
    2. The candidate is executed against the target database.
    3. While execution fails and the repair budget lasts, the verbatim database
       error message, the failing query, the schema, the question and a
       targeted hint derived from the error are packed into a repair prompt;
       the solver regenerates the query and the new candidate is re-executed.
    4. The loop stops on the first successful execution, when the solver
       converges back to the identical failing statement, or when the repair
       budget is exhausted; the most recent candidate is returned.
    """

    MAX_REPAIRS = 4
    MAX_ERROR_CHARS = 600

    SYSTEM = (
        "You are a careful SQLite expert. Given a database schema and a "
        "natural-language question, you answer with exactly one SQL SELECT "
        "statement that runs without errors on that schema. Use only the "
        "tables, columns and SQLite functions that the schema justifies. "
        "Output the SQL statement by itself, with no explanation."
    )

    def solve(self, question: str) -> str:
        sql = self._generate_initial(question)
        outcome = self._evaluate(sql)

        repairs = 0
        while not outcome["ok"] and repairs < self.MAX_REPAIRS:
            candidate = self._generate_repair(
                question, sql, outcome["error"], repairs + 1
            )
            if not candidate or candidate == sql:
                # The solver produced nothing new (or nothing at all); running
                # the identical statement again would just repeat the error.
                break
            sql = candidate
            outcome = self._evaluate(sql)
            repairs += 1

        # Best effort: the most recent candidate, executed or not.
        return sql

    # ------------------------------------------------------------------
    # generation
    # ------------------------------------------------------------------

    def _generate_initial(self, question: str) -> str:
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL SELECT query that answers the question using this "
            "schema. Return only the SQL."
        )
        raw = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        return self._clean(bridge.extract_sql(raw))

    def _generate_repair(
        self, question: str, bad_sql: str, error: str, attempt: int
    ) -> str:
        if len(error) > self.MAX_ERROR_CHARS:
            error = error[: self.MAX_ERROR_CHARS].rstrip() + " ...[truncated]"
        hint = self._hint(error)
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "A SQL query was written for this question, but the database "
            "rejected it with the error shown below.\n\n"
            f"Failed query:\n{bad_sql}\n\n"
            f"Database error:\n{error}\n\n"
            f"Repair attempt {attempt}: rewrite the query so that it executes "
            "without errors on the schema above and still answers the question. "
            "Re-check every table and column name against the schema, fix the "
            "syntax, quoting, JOIN and GROUP BY issues the error points at, and "
            "avoid functions SQLite does not provide. "
            "Return only the corrected SQL."
        )
        if hint:
            prompt += f"\n\nHint: {hint}"
        raw = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        return self._clean(bridge.extract_sql(raw))

    # ------------------------------------------------------------------
    # execution / verification
    # ------------------------------------------------------------------

    def _evaluate(self, sql: str) -> dict:
        """Execute a candidate and normalize the outcome into a dict."""
        if not sql:
            return {
                "ok": False,
                "rows": [],
                "error": "no SQL statement could be extracted from the solver output",
            }
        try:
            result = self.execute(sql)
        except Exception as exc:  # engine crash -> treat as a repairable failure
            return {"ok": False, "rows": [], "error": f"execution raised {exc!r}"}
        if not isinstance(result, dict):
            return {
                "ok": False,
                "rows": [],
                "error": "execution returned an unusable result",
            }
        return {
            "ok": bool(result.get("ok")),
            "rows": result.get("rows") or [],
            "error": str(result.get("error") or "").strip()
            or "execution failed (no error message was reported)",
        }

    # ------------------------------------------------------------------
    # utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _hint(error: str) -> str:
        """A short, error-class-specific nudge appended to the repair prompt."""
        e = error.lower()
        if "no such column" in e:
            return (
                "The error names a column that does not exist; use only the "
                "exact column names defined in the schema, qualified with "
                "their table when needed."
            )
        if "no such table" in e:
            return (
                "The error names a table that does not exist; use one of the "
                "tables defined in the schema."
            )
        if "no such function" in e:
            return (
                "The error names a function SQLite does not provide; rewrite "
                "the expression using built-in SQLite functions."
            )
        if "wrong number of arguments" in e:
            return (
                "A function is called with the wrong argument count; check "
                "its SQLite signature."
            )
        if "ambiguous" in e:
            return "A column name is ambiguous; qualify it with its table name."
        if "aggregate" in e or "group by" in e:
            return (
                "Reconcile aggregate and non-aggregate columns: every "
                "non-aggregated selected column must appear in GROUP BY."
            )
        if "syntax error" in e or "near" in e:
            return (
                "This is a syntax problem; simplify the statement and check "
                "SQLite syntax around the reported token."
            )
        return ""

    @staticmethod
    def _clean(sql: str) -> str:
        sql = (sql or "").strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql