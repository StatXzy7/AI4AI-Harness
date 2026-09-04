"""Repair harness: generate SQLite from the schema and question, execute it, and if execution fails, feed the exact SQLite error back to the LLM and regenerate, for up to 2 repair rounds."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS1Repair"]


class P2P2DGlmS1Repair(SQLHarness):
    """Weak Text-to-SQL solver with execution-guided, error-feedback repair (max 2 retries)."""

    # Number of regeneration attempts AFTER the initial generation.
    MAX_REPAIRS = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. Using the provided database schema, "
        "write exactly one SQLite query that answers the user's question. "
        "Output only the SQL query."
    )

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #

    def _initial_prompt(self, question: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQLite query that answers this question. "
            "Respond with the SQL query only."
        )

    def _repair_prompt(self, question: str, failed_sql: str, error: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "A previous attempt produced this SQLite query:\n"
            f"{failed_sql}\n\n"
            "Executing it against the database failed with this exact SQLite error:\n"
            f"{error}\n\n"
            "Rewrite the query so that it executes successfully against the schema "
            "and still answers the question. Respond with the corrected SQL query only."
        )

    # ------------------------------------------------------------------ #
    # LLM helper
    # ------------------------------------------------------------------ #

    def _generate_sql(self, prompt: str) -> str:
        text = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        if isinstance(text, list):  # defensive: some bridges return a list even for n=1
            text = text[0]
        return bridge.extract_sql(text)

    # ------------------------------------------------------------------ #
    # Main control flow: generate -> execute -> repair on error
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        # --- Phase 1: initial generation ------------------------------ #
        prompt = self._initial_prompt(question)
        sql = self._generate_sql(prompt)

        # --- Phase 2: execute; on failure, repair with the exact error - #
        result = self.execute(sql)

        repairs = 0
        while not result.get("ok") and repairs < self.MAX_REPAIRS:
            repairs += 1
            error = result.get("error") or "unknown execution error"
            prompt = self._repair_prompt(question, sql, error)
            sql = self._generate_sql(prompt)
            result = self.execute(sql)

        # Whether or not the final query executes, it is our best answer.
        return sql