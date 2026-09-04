"""Harness that generates SQL, executes it, and repairs failures by feeding execution errors back to the LLM for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS0G1(SQLHarness):
    """Generate SQL greedily, execute it, and on execution error loop the
    error message back into the prompt so the LLM can repair the query."""

    MAX_ATTEMPTS = 4  # 1 initial generation + up to 3 repair rounds

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL assistant. Given a database "
            "schema and a natural-language question, write a single correct "
            "SQLite query. Output only the SQL query, with no explanation."
        )
        base_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL query that answers the question."
        )

        prompt = base_prompt
        last_sql = ""
        for _attempt in range(self.MAX_ATTEMPTS):
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
            text = response[0] if isinstance(response, (list, tuple)) else response
            sql = bridge.extract_sql(text) or (text or "").strip()

            if not sql:
                # Nothing extractable: reprompt once with a stricter instruction.
                prompt = (
                    base_prompt
                    + "\n\nYour previous reply contained no SQL. "
                      "Output only the SQL query."
                )
                continue

            last_sql = sql
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            # Repair step: feed the failing SQL and its error back to the LLM.
            error = result.get("error", "unknown execution error")
            prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Your previous SQL query failed to execute.\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Execution error:\n{error}\n\n"
                "Diagnose the cause of the error (e.g., wrong table or column "
                "names, bad joins, invalid syntax) and rewrite the query. "
                "Output only the corrected SQL query."
            )

        # All attempts exhausted: return the best (most recent) candidate.
        return last_sql