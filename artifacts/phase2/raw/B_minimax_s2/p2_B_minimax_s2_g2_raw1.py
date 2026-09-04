"""Iterative repair harness that feeds SQL execution errors back to the LLM for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G2(SQLHarness):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._max_repairs = 4

    def solve(self, question: str) -> str:
        system_prompt = (
            "You are an expert SQL engineer. Given a database schema and a natural language "
            "question, produce exactly one valid SQL query that answers the question. "
            "Output ONLY the SQL statement with no prose, no markdown fences, and no explanation."
        )

        # Initial generation
        prompt = self._build_initial_prompt(question)
        raw = self.llm(prompt, system=system_prompt, temperature=0.0, n=1)
        current_sql = bridge.extract_sql(raw)

        # Repair loop: execute and feed errors back
        for attempt in range(self._max_repairs):
            result = self.execute(current_sql)

            if result.get("ok"):
                # Query executed successfully; verify it returns rows
                rows = result.get("rows", [])
                if rows is not None and len(rows) > 0:
                    return current_sql
                # Empty result set may indicate a logic error; try repairing
                feedback = "The query executed but returned an empty result set. The query may have incorrect logic, wrong predicates, or wrong table joins."
            else:
                error_msg = result.get("error", "unknown execution error")
                feedback = f"SQL execution failed with error: {error_msg}"

            # Build a repair prompt with the previous attempt and error feedback
            repair_prompt = self._build_repair_prompt(question, current_sql, feedback, attempt)
            raw = self.llm(repair_prompt, system=system_prompt, temperature=0.0, n=1)
            new_sql = bridge.extract_sql(raw)

            # Sanity check: ensure we got something different and non-empty
            if not new_sql or new_sql.strip() == current_sql.strip():
                # Model failed to improve; try once more with higher temperature for diversity
                raw = self.llm(repair_prompt, system=system_prompt, temperature=0.3, n=1)
                new_sql = bridge.extract_sql(raw)

            if not new_sql:
                # Give up on this attempt; keep what we have
                break

            current_sql = new_sql

        return current_sql

    def _build_initial_prompt(self, question: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a SQL query that answers this question. Return only the SQL."
        )

    def _build_repair_prompt(self, question: str, previous_sql: str, feedback: str, attempt: int) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Your previous SQL attempt was:\n{previous_sql}\n\n"
            f"Feedback from execution (attempt {attempt + 1}):\n{feedback}\n\n"
            f"Produce a corrected SQL query that fixes the issue. Return only the corrected SQL."
        )