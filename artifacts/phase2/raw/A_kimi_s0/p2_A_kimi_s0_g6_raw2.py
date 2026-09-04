"""Repair-loop Text-to-SQL harness: generate a query, execute it, and feed any execution error back to the LLM to regenerate a corrected query."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G6(SQLHarness):
    """Generate SQL greedily, then iteratively repair it using real execution errors."""

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite query writer. Given a database schema and a "
            "natural-language question, you produce exactly one correct SQL query. "
            "Reply with only the SQL query itself: no explanation, no comments, no "
            "markdown fences."
        )
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. Output only the SQL."
        )

        prompt = base_prompt
        last_sql = ""
        last_error = ""

        for _ in range(self.MAX_ATTEMPTS):
            response = self.llm(prompt, system=system, temperature=0.0)
            sql = bridge.extract_sql(response)

            if not sql:
                # Extraction failed: ask again, keeping the loop bounded.
                prompt = (
                    f"{base_prompt}\n\n"
                    "Your previous reply did not contain a SQL query. "
                    "Reply with ONLY the SQL query, nothing else."
                )
                continue

            last_sql = sql
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            error = (result.get("error") or "unknown error").strip()
            if error == last_error:
                # Same failure twice: nudge with sampling to break the cycle.
                response = self.llm(prompt, system=system, temperature=0.7)
                alt_sql = bridge.extract_sql(response)
                if alt_sql and alt_sql != sql and self.execute(alt_sql).get("ok"):
                    return alt_sql
            last_error = error

            # Feed the real execution error back and request a corrected query.
            prompt = (
                f"{base_prompt}\n\n"
                "Your previous SQL query failed to execute.\n"
                "Faulty SQL:\n"
                f"{sql}\n\n"
                "Database error message:\n"
                f"{error}\n\n"
                "Diagnose why it failed using the schema above, then reply with "
                "ONLY the corrected SQL query."
            )

        # All attempts exhausted: return the best-effort query rather than nothing.
        return last_sql