"""Generate SQL, execute it against the database, and on failure feed the exact SQLite error back to the LLM for up to two repair attempts."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2Repair(SQLHarness):
    """Weak-solver Text-to-SQL harness with execution-guided self-repair.

    Control flow:
      1. Generate an initial SQL candidate from schema + question.
      2. Execute it via self.execute().
      3. If execution fails, build a repair prompt containing the failed SQL
         and the exact SQLite error message, then regenerate.
      4. Repeat step 3 at most MAX_REPAIRS times.
      5. Return the first SQL that executes successfully; otherwise return the
         last candidate as a best-effort fallback.
    """

    MAX_REPAIRS = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite text-to-SQL assistant. Given a database "
        "schema and a natural-language question, produce a single valid "
        "SQLite query that answers the question. Output only the SQL query, "
        "with no explanations, comments, or markdown fences."
    )

    def _build_prompt(self, question: str, failed_sql: str = "", error: str = "") -> str:
        """Assemble the generation prompt, optionally augmented with failure feedback."""
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n"
        )
        if failed_sql and error:
            prompt += (
                "\nA previous attempt produced this SQL query:\n"
                f"{failed_sql}\n\n"
                "Executing it in SQLite failed with this exact error:\n"
                f"{error}\n\n"
                "Diagnose the cause of the error and rewrite the query so it "
                "executes correctly while still answering the question. "
            )
        prompt += "\nWrite the corrected SQLite query now:"
        return prompt

    def _generate(self, prompt: str) -> str:
        """Call the frozen LLM and extract a clean SQL string from its output."""
        response = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""
        return bridge.extract_sql(str(response))

    def solve(self, question: str) -> str:
        # Initial generation.
        sql = self._generate(self._build_prompt(question))
        result = self.execute(sql)
        if result.get("ok"):
            return sql

        # Execution-guided repair loop: feed back the exact SQLite error.
        for _ in range(self.MAX_REPAIRS):
            error = result.get("error") or "Unknown SQLite error"
            repair_prompt = self._build_prompt(question, failed_sql=sql, error=error)
            sql = self._generate(repair_prompt)
            result = self.execute(sql)
            if result.get("ok"):
                return sql

        # All attempts failed; return the last candidate as best effort.
        return sql