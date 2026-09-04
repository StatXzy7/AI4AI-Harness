"""Repair loop: the harness greedily generates one SQL statement, executes it, and feeds any execution error back to the frozen LLM for up to two regeneration attempts before falling back to the last candidate."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G2(SQLHarness):
    """Text-to-SQL harness with an execution-error repair loop.

    Control flow (a real change vs. a single greedy call):

      1. Ask the frozen solver for one SQLite statement (temperature 0.0).
      2. Execute that statement on the real database via ``self.execute``.
      3. If -- and only if -- execution fails, build a repair prompt that
         contains the schema, the question, the failing SQL and the *verbatim*
         database error, and ask the solver to rewrite the statement.
      4. Repeat for up to ``MAX_ATTEMPTS`` generations total; the final
         attempt is sampled slightly above zero so the model does not simply
         parrot the same broken statement.
      5. Return the first statement that executes cleanly; if every attempt
         fails, return the most recent candidate.
    """

    MAX_ATTEMPTS = 3
    #: per-attempt sampling temperature (last attempt is slightly diversified)
    TEMPERATURES = (0.0, 0.0, 0.3)
    #: keep the fed-back error string bounded
    MAX_ERROR_CHARS = 600

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL engine. Given a database schema and a "
        "natural-language question, produce exactly one SQLite SELECT statement "
        "that answers the question. Respond with the SQL statement only: no "
        "explanation, no comments, no markdown."
    )

    # ------------------------------------------------------------------
    # prompt construction
    # ------------------------------------------------------------------

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "----------------\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQLite statement:"
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            "Database schema:\n"
            "----------------\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "A previous attempt produced this SQLite statement:\n"
            "---------------------------------------------------\n"
            f"{bad_sql}\n\n"
            "Executing it on the database failed with this error:\n"
            "-----------------------------------------------------\n"
            f"{error}\n\n"
            "The statement is invalid for this schema (wrong table or column "
            "name, bad quoting, bad JOIN condition, ...). Rewrite it as ONE "
            "correct SQLite SELECT statement that answers the question. "
            "Respond with the SQL statement only."
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _generate_sql(self, prompt: str, attempt: int) -> str:
        temperature = self.TEMPERATURES[min(attempt, len(self.TEMPERATURES) - 1)]
        text = self.llm(
            prompt, system=self.SYSTEM_PROMPT, temperature=temperature, n=1
        )
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        if not isinstance(text, str):
            text = "" if text is None else str(text)

        sql = (bridge.extract_sql(text) or "").strip()
        # tolerate stray code fences that some models emit around the SQL
        while len(sql) >= 2 and sql.startswith("`") and sql.endswith("`"):
            sql = sql[1:-1].strip()
        if sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    def _run(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: the harness must never crash
            return {"ok": False, "rows": [], "error": f"harness exception: {exc}"}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "executor returned no result"}
        return result

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------

    def solve(self, question: str) -> str:
        best_sql = ""
        feedback = None  # becomes {"sql": ..., "error": ...} after a failure

        for attempt in range(self.MAX_ATTEMPTS):
            if feedback is None:
                prompt = self._initial_prompt(question)
            else:
                prompt = self._repair_prompt(
                    question, feedback["sql"], feedback["error"]
                )

            sql = self._generate_sql(prompt, attempt)
            if not sql:
                # Nothing extractable from the model output: treat this as a
                # failed attempt and let the repair prompt try again.
                feedback = {
                    "sql": "(the previous response contained no SQL statement)",
                    "error": (
                        "Execution failed: no SQL statement could be extracted "
                        "from the previous response."
                    ),
                }
                continue

            best_sql = sql

            result = self._run(sql)
            if result.get("ok"):
                return sql  # success: stop immediately

            raw_error = result.get("error") or "Unknown execution error."
            if len(raw_error) > self.MAX_ERROR_CHARS:
                raw_error = raw_error[: self.MAX_ERROR_CHARS] + " ...[truncated]"
            feedback = {"sql": sql, "error": raw_error}

        # Every attempt failed: hand back the most recent candidate so the
        # caller still receives a syntactically plausible SQL string.
        return best_sql