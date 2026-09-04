"""Text-to-SQL harness that greedily generates SQL, executes it against the database, and repairs failures by feeding the SQLite error message back to the LLM for up to three regeneration rounds."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G7(SQLHarness):
    """Greedy generation hardened with an execution-feedback repair loop.

    Control flow (a real change vs. a single greedy call):

      1. one greedy LLM call produces a candidate SQL statement,
      2. the candidate is validated (must be a read-only SELECT/WITH query)
         and then executed against the real database,
      3. if validation or execution fails, the engine's error message is
         placed into a repair prompt and the LLM regenerates the query,
      4. steps 2-3 repeat up to ``MAX_REPAIR_ROUNDS`` times; the first
         candidate that executes cleanly is returned immediately.

    Degenerate loops (the model repeating an already-failed query) are
    detected and cut short, so the harness makes at most
    ``1 + MAX_REPAIR_ROUNDS`` LLM calls and executes each distinct
    candidate at most once.
    """

    MAX_REPAIR_ROUNDS = 3
    MAX_ERROR_CHARS = 500
    FALLBACK_SQL = "SELECT 1"

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "question, you output exactly one SQLite SELECT statement that answers "
        "the question, using only tables and columns present in the schema."
    )

    # ------------------------------------------------------------------
    # main control flow
    # ------------------------------------------------------------------

    def solve(self, question: str) -> str:
        question = (question or "").strip()

        last_sql = ""    # most recent SQL the model actually produced
        tried = set()    # candidates already attempted (all of them failed)
        prompt = self._initial_prompt(question)

        # 1 greedy call + at most MAX_REPAIR_ROUNDS repair calls
        for _ in range(1 + self.MAX_REPAIR_ROUNDS):
            text = self._call(prompt)
            candidate = self._tidy(self._extract(text))

            if candidate and candidate not in tried:
                tried.add(candidate)
                last_sql = candidate

                # static validation: never send non-queries to the engine
                error = self._check(candidate)
                if error is None:
                    outcome = self._run(candidate)
                    if outcome.get("ok"):
                        return candidate          # clean execution: ship it
                    error = self._describe(outcome)

            elif candidate:
                # model repeated an already-failed query; further rounds
                # are pointless, stop early
                break

            else:
                error = "the previous reply contained no SQL statement"

            # feed the failure back and regenerate
            prompt = self._repair_prompt(question, last_sql, error)

        return last_sql or self.FALLBACK_SQL

    # ------------------------------------------------------------------
    # LLM plumbing
    # ------------------------------------------------------------------

    def _call(self, prompt: str) -> str:
        """One greedy LLM call; tolerates list-shaped or None responses."""
        try:
            out = self.llm(prompt, system=self.SYSTEM_PROMPT,
                           temperature=0.0, n=1)
        except TypeError:
            # older llm signature without keyword arguments
            out = self.llm(prompt)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if out is None:
            return ""
        return out if isinstance(out, str) else str(out)

    # ------------------------------------------------------------------
    # SQL plumbing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract(text: str) -> str:
        """Pull the SQL out of the model reply via the bridge."""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            return ""
        return sql or ""

    @staticmethod
    def _tidy(sql: str) -> str:
        """Normalise whitespace and drop trailing semicolons."""
        if not sql:
            return ""
        sql = sql.strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    @staticmethod
    def _check(sql: str):
        """Return None for read-only queries, else a repair error message."""
        head = sql.lstrip("( \t\r\n").upper()
        if head.startswith("SELECT") or head.startswith("WITH"):
            return None
        return ("the statement is not a read-only SELECT query; "
                "output a single SELECT statement")

    def _run(self, sql: str) -> dict:
        """Execute a candidate, never raising, always returning a dict."""
        if not sql:
            return {"ok": False, "rows": [], "error": "empty SQL"}
        try:
            outcome = self.execute(sql)
        except Exception as exc:
            # the executor blew up outright: treat as a normal failure
            return {"ok": False, "rows": [], "error": "executor raised: %s" % exc}
        if not isinstance(outcome, dict):
            return {"ok": False, "rows": [], "error": "no execution result"}
        return outcome

    def _describe(self, outcome: dict) -> str:
        """Render the execution error for the repair prompt, truncated."""
        error = str(outcome.get("error") or "").strip()
        if not error:
            error = "the query failed to execute"
        if len(error) > self.MAX_ERROR_CHARS:
            error = error[: self.MAX_ERROR_CHARS] + " ..."
        return error

    # ------------------------------------------------------------------
    # prompt builders
    # ------------------------------------------------------------------

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "%s\n\n"
            "Question: %s\n\n"
            "Write ONE SQLite SELECT statement that answers the question.\n"
            "Rules:\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Output only the SQL inside a