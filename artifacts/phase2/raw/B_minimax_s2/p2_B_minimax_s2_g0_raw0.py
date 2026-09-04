# MECHANISM: repair
"""Repair-based harness: execute generated SQL, feed errors back to LLM for regeneration."""

import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        system_prompt = (
            "You are a Text-to-SQL expert. Given a database schema and a natural language "
            "question, produce a single SQLite-compatible SQL query. Output ONLY the SQL, "
            "no markdown fences, no explanations."
        )

        user_prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL query that answers this question. Output only the SQL."
        )

        max_attempts = 3
        last_sql = ""
        last_error = ""

        for attempt in range(max_attempts):
            if last_error:
                repair_prompt = (
                    f"{user_prompt}\n\n"
                    f"Your previous attempt produced this SQL:\n{last_sql}\n\n"
                    f"When executed against the database it failed with this error:\n"
                    f"{last_error}\n\n"
                    "Identify the problem and produce a corrected SQL query. "
                    "Output only the corrected SQL."
                )
                prompt = repair_prompt
            else:
                prompt = user_prompt

            response = self.llm(
                prompt,
                system=system_prompt,
                temperature=0.0,
                n=1,
            )
            sql = bridge.extract_sql(response)
            if not sql:
                sql = response.strip()
                # strip code fences if present
                sql = re.sub(r"^