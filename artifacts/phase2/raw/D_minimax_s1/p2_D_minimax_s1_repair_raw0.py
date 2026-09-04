"""Harness that generates SQL, executes it, and repairs on SQLite errors by re-prompting with the error message up to two times."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS1Repair(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial generation prompt
        prompt = (
            "Given the following SQLite schema and a natural language question, "
            "write a single SQL query that answers the question. "
            "Return ONLY the SQL query with no explanation, no markdown, and no code fences.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )

        sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_text)

        max_repairs = 2
        for attempt in range(max_repairs + 1):
            # Execute the current candidate SQL
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            # If we've already exhausted repairs, return the last attempt anyway
            if attempt >= max_repairs:
                return sql

            # Build a repair prompt that includes the exact SQLite error
            error_msg = result.get("error", "")
            repair_prompt = (
                "The following SQL query failed to execute in SQLite. "
                "Diagnose the error from the message below and return a corrected SQL query. "
                "Return ONLY the corrected SQL query with no explanation, no markdown, and no code fences.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Original question: {question}\n\n"
                f"Failed SQL:\n{sql}\n\n"
                f"SQLite error:\n{error_msg}\n\n"
                "Corrected SQL:"
            )

            repaired_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            repaired_sql = bridge.extract_sql(repaired_text)
            if not repaired_sql:
                # If extraction failed, stop trying to avoid infinite/no-progress loops
                return sql
            sql = repaired_sql

        return sql