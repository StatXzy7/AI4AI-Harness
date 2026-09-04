"""Generate SQL, execute it, and repair failures by feeding execution errors back to the LLM for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS1G0(SQLHarness):
    """Execution-feedback repair harness for Text-to-SQL.

    Control flow:
      1. Greedy generation of an initial SQL candidate.
      2. Execute the candidate against the database.
      3. If execution fails, build a repair prompt containing the failed SQL
         and the database's error message, and regenerate.
      4. Repeat until a query executes successfully or the attempt budget
         is exhausted; return the best (last) candidate otherwise.
    """

    MAX_ATTEMPTS = 4  # execution-and-repair rounds after the initial generation

    def _generate(self, prompt: str, system: str, temperature: float) -> str:
        """Call the frozen solver LLM and extract a SQL string from its output."""
        text = self.llm(prompt, system=system, temperature=temperature)
        return bridge.extract_sql(text)

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL engine. "
            "You output exactly one SQL query and nothing else."
        )

        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. Output only the SQL."
        )

        # Stage 1: initial greedy candidate.
        sql = self._generate(base_prompt, system, temperature=0.0)

        # Stage 2: execute-and-repair loop.
        for _ in range(self.MAX_ATTEMPTS):
            if not sql:
                # Extraction produced nothing; ask again with slight diversity.
                sql = self._generate(base_prompt, system, temperature=0.3)
                continue

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error") or "unknown execution error"
            repair_prompt = (
                "Database schema:\n"
                f"{self.schema}\n\n"
                f"Question: {question}\n\n"
                "This SQL query was tried:\n"
                "