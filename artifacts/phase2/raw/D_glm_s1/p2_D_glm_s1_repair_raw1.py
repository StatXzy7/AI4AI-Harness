"""Generate a candidate SQLite query, execute it, and on failure feed the exact SQLite error back to the LLM to regenerate the query, for up to two repair rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS1Repair(SQLHarness):
    """Generate a candidate SQLite query, execute it, and on failure feed the exact SQLite error back to the LLM to regenerate the query, for up to two repair rounds."""

    MAX_REPAIR_ATTEMPTS = 2

    SYSTEM_PROMPT = (
        "You are an expert data analyst who writes correct SQLite queries. "
        "Always answer with exactly one SQL query and nothing else."
    )

    def solve(self, question: str) -> str:
        last_sql = ""
        last_error = ""

        # 1 initial generation + at most MAX_REPAIR_ATTEMPTS regenerations.
        for attempt in range(1 + self.MAX_REPAIR_ATTEMPTS):
            if attempt == 0:
                prompt = self._initial_prompt(question)
            else:
                prompt = self._repair_prompt(question, last_sql, last_error)

            raw = self._call_llm(prompt)
            sql = (bridge.extract_sql(raw) or "").strip()

            if not sql:
                last_error = "The previous answer contained no SQL statement to execute."
                continue

            last_sql = sql
            result = self._execute(sql)

            if result.get("ok"):
                return sql

            last_error = str(
                result.get("error") or "Unknown SQLite execution error."
            ).strip()

        # All attempts failed: return the best-effort (last generated) SQL.
        return last_sql

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _initial_prompt(self, question: str) -> str:
        return (
            "You are given the schema of a SQLite database and a question.\n"
            "Write a single SQL query that answers the question.\n"
            "\n"
            "Database schema:\n"
            f"{self.schema}\n"
            "\n"
            f"Question: {question}\n"
            "\n"
            "Rules:\n"
            "- Use SQLite syntax only.\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Return exactly one SQL query, wrapped in a