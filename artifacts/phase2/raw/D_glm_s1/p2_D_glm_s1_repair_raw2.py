"""Generate SQL, execute it against the database, and on failure re-prompt the model with the exact SQLite error to regenerate a fixed query, up to two times."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS1Repair(SQLHarness):
    """Execute-guided self-repair harness: generate -> execute -> feed the exact
    SQLite error back into the prompt -> regenerate, with at most 2 repair rounds
    (i.e. at most 3 LLM generations in total)."""

    # Number of allowed regenerations after a failed execution.
    # Total LLM calls = 1 (initial) + MAX_REPAIRS.
    MAX_REPAIRS = 2

    _SYSTEM = (
        "You are an expert SQLite programmer. Using only the schema provided, "
        "write exactly one SQL query (a single SELECT statement) that answers "
        "the user's question. Respond with the SQL query only -- no markdown, "
        "no commentary, no extra text."
    )

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #
    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL query that answers the question."
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "You previously wrote this SQL query:\n"
            f"{bad_sql}\n\n"
            "Executing it against the SQLite database failed with this exact error:\n"
            f"{error}\n\n"
            "Rewrite the query so that it executes successfully and still answers "
            "the question. Respond with the corrected SQL query only -- no markdown, "
            "no commentary, no extra text."
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _call_llm(self, prompt: str) -> str:
        """Call the LLM and normalize the output to a plain string."""
        raw = self.llm(prompt, system=self._SYSTEM, temperature=0.0, n=1)
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        return raw if isinstance(raw, str) else str(raw)

    def _run_sql(self, sql: str) -> dict:
        """Execute SQL defensively; never let execute() break the repair loop."""
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: surface as a normal failure
            result = {"ok": False, "rows": [], "error": str(exc)}
        return result or {}

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        prompt = self._initial_prompt(question)
        final_sql = ""
        last_text = ""

        # 1 initial generation + up to MAX_REPAIRS regenerations.
        for attempt in range(self.MAX_REPAIRS + 1):
            # 1) Generate SQL from the current prompt.
            last_text = self._call_llm(prompt)
            sql = bridge.extract_sql(last_text) or ""
            if sql:
                final_sql = sql

            # 2) Execute the generated SQL.
            if sql:
                result = self._run_sql(sql)
                if result.get("ok"):
                    # Success: return the executing SQL immediately.
                    return sql
                # 3) Failure: capture the exact SQLite error to feed back.
                error = str(result.get("error") or "Unknown SQLite execution error.")
            else:
                error = "No SQL statement could be extracted from the response."

            # Regenerate only while repair budget remains.
            if attempt < self.MAX_REPAIRS:
                prompt = self._repair_prompt(
                    question, sql or last_text.strip(), error
                )

        # All attempts failed (or produced nothing executable): return the best
        # SQL we ever extracted, falling back to the raw model output.
        if not final_sql:
            final_sql = last_text.strip()
        return final_sql