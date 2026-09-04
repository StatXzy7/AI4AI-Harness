"""Text-to-SQL harness with an execution-feedback repair loop: a greedy first candidate is executed against the database, and any error (or unusable output) is fed back with the schema for up to three corrective regenerations."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G6(SQLHarness):
    """Greedy generation wrapped in an execute-and-repair control loop.

    Per question:
      1. one greedy LLM call produces a candidate SQL string;
      2. the candidate is executed against the real database;
      3. if execution fails -- or the model emitted nothing usable or a
         non-read-only statement -- the error text, the offending query
         and every earlier failure are packaged into a repair prompt and
         the solver regenerates;
      4. steps 2-3 repeat at most ``MAX_REPAIRS`` times; the first query
         that executes cleanly is returned immediately, otherwise the
         last attempt (the one produced with the richest feedback) is
         returned as the fallback.
    """

    MAX_REPAIRS = 3  # 1 initial generation + up to 3 repair rounds

    SYSTEM = (
        "You are an expert SQLite analyst. Reply with exactly one SQL "
        "query and nothing else: no explanations, no markdown, no code "
        "fences."
    )

    # --------------------------------------------------------------- public

    def solve(self, question: str) -> str:
        failures = []  # [(sql, error)] in attempt order
        last_sql = ""

        sql = self._generate(self._prompt_first(question))
        for attempt in range(1 + self.MAX_REPAIRS):
            last_sql = sql

            # Cheap static gate before touching the database.
            error = self._static_check(sql)
            if error is None:
                result = self._run(sql)
                if result.get("ok"):
                    return sql  # clean execution -> ship it
                error = (result.get("error") or "execution failed").strip()

            # Record the failure; it becomes feedback for the next round.
            failures.append((sql, error))
            if attempt < self.MAX_REPAIRS:
                sql = self._generate(self._prompt_repair(question, failures))

        # Every attempt failed. Return the most recent one: it was produced
        # with the fullest error feedback and is the model's best effort.
        return last_sql

    # -------------------------------------------------------------- prompts

    def _prompt_first(self, question):
        schema = self.schema if self.schema else "(no schema provided)"
        return (
            "Database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite SELECT query that answers the question.\n"
            "Use only tables and columns that appear in the schema.\n"
            "Reply with the SQL query only."
        )

    def _prompt_repair(self, question, failures):
        schema = self.schema if self.schema else "(no schema provided)"
        parts = [
            "Database schema:",
            schema,
            "",
            f"Question: {question}",
            "",
            "The SQL written for this question failed to execute on the "
            "database. Every attempt and its execution error is listed "
            "below:",
            "",
        ]
        for i, (sql, err) in enumerate(failures, 1):
            parts.append(f"Attempt {i}:")
            parts.append(sql if sql else "(the model returned no SQL)")
            parts.append(f"Error: {err}")
            parts.append("")
        parts.append(
            "Write a corrected SQLite SELECT query that fixes the reported "
            "errors. Re-check table names, column names, join conditions "
            "and quoting against the schema, and do not repeat any "
            "previously attempted query. Reply with the SQL query only."
        )
        return "\n".join(parts)

    # -------------------------------------------------------------- helpers

    def _generate(self, prompt):
        """One greedy LLM call -> cleaned SQL string ('' on any failure)."""
        try:
            raw = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
            sql = bridge.extract_sql(self._as_text(raw))
        except Exception:
            return ""
        return self._clean(sql)

    def _run(self, sql):
        """Execute defensively: a raising executor must not kill the loop."""
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": f"executor raised: {exc}"}

    def _static_check(self, sql):
        """Return an error string for unusable SQL, otherwise None."""
        if not sql:
            return "No SQL statement was found in the model output."
        if not self._is_readonly(sql):
            return ("The statement is not a read-only query; only "
                    "SELECT / WITH / VALUES statements may be executed.")
        return None

    @staticmethod
    def _is_readonly(sql):
        s = sql.strip()
        while s.startswith("("):
            s = s[1:].lstrip()
        head = s.split(None, 1)[0].upper() if s else ""
        return head in ("SELECT", "WITH", "VALUES")

    @staticmethod
    def _as_text(raw):
        """Normalize LLM output (some backends return a list for n=1)."""
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        if raw is None:
            return ""
        return raw if isinstance(raw, str) else str(raw)

    @staticmethod
    def _clean(sql):
        if not sql:
            return ""
        text = sql.strip()
        while text.endswith(";"):
            text = text[:-1].rstrip()
        return text