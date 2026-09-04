"""GLM-S2 Text-to-SQL harness: generate SQL, execute it against the SQLite database, and if execution fails, feed the exact SQLite error message back to the LLM for up to 2 repair regenerations."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2Repair"]


class P2P2DGlmS2Repair(SQLHarness):
    """Weak-solver wrapper implementing a generate -> execute -> repair loop.

    Mechanism (realized in control flow, not just the prompt):
      1. Ask the LLM for a single SQL query given the schema and question.
      2. Execute that query via ``self.execute``.
      3. If execution fails, show the LLM the failed query plus the *exact*
         SQLite error and regenerate. At most 2 repair rounds are attempted;
         the first query that executes successfully is returned immediately.
    """

    MAX_REPAIRS = 2  # number of regeneration attempts after the initial one

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. "
        "Reply with exactly one SQL query and nothing else: "
        "no explanation, no markdown fences, no comments."
    )

    # ------------------------------------------------------------------ #
    # Prompt builders
    # ------------------------------------------------------------------ #

    def _initial_prompt(self, question: str) -> str:
        return "\n".join(
            [
                "You are querying a SQLite database.",
                "",
                "Schema:",
                self.schema,
                "",
                "Question:",
                question,
                "",
                "Write a single SQL query that answers the question.",
                "Output only the SQL query.",
            ]
        )

    def _repair_prompt(self, question: str, failed_sql: str, error: str) -> str:
        # The exact, unmodified error string from self.execute is embedded here.
        return "\n".join(
            [
                "You are querying a SQLite database.",
                "",
                "Schema:",
                self.schema,
                "",
                "Question:",
                question,
                "",
                "Your previous SQL query FAILED to execute on this database.",
                "",
                "Failed SQL query:",
                failed_sql,
                "",
                "Exact SQLite error message:",
                error,
                "",
                "Write a corrected SQL query that answers the question and executes "
                "without errors on this schema.",
                "Output only the SQL query.",
            ]
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _generate(self, prompt: str) -> str:
        """One LLM call; returns the extracted, whitespace-stripped SQL string."""
        out = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):  # some backends return a list even for n=1
            out = out[0] if out else ""
        return bridge.extract_sql(out or "").strip()

    def _run(self, sql: str) -> dict:
        """Execute ``sql`` without ever raising; always returns a result dict."""
        if not sql:
            return {"ok": False, "rows": [], "error": "no SQL query was produced"}
        try:
            return self.execute(sql)
        except Exception as exc:  # defensive: executor crashes count as failures
            return {"ok": False, "rows": [], "error": "executor raised: %s" % exc}

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        # --- Step 1: initial generation --------------------------------- #
        sql = self._generate(self._initial_prompt(question))

        last_nonempty = sql
        repairs_used = 0

        # --- Step 2: execute; on failure, repair with the exact error -- #
        while True:
            result = self._run(sql)

            # Query executed successfully -> accept it immediately.
            if result.get("ok"):
                return sql

            if sql:
                last_nonempty = sql

            # Repair budget exhausted -> return best-effort SQL.
            if repairs_used >= self.MAX_REPAIRS:
                # Prefer the last attempt; fall back to the last parseable
                # candidate; ultimate fallback guarantees an executable string.
                return sql or last_nonempty or "SELECT 1;"

            # Feed the exact SQLite error back to the LLM and regenerate.
            repairs_used += 1
            error = str(result.get("error") or "unknown execution error")
            sql = self._generate(
                self._repair_prompt(question, failed_sql=sql, error=error)
            )