"""Generate SQL, execute it, and on failure feed the SQLite error back to the LLM for up to two repair attempts."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0Repair(SQLHarness):
    def solve(self, question: str) -> str:
        system_prompt = (
            "You are a Text-to-SQL assistant. Given a database schema and a natural "
            "language question, produce a single SQLite-compatible SQL query that "
            "answers the question. Output ONLY the SQL statement, with no markdown "
            "fences, no commentary, and no explanation."
        )

        def build_repair_system(extra: str = "") -> str:
            if not extra:
                return system_prompt
            return system_prompt + "\n\n" + extra

        # Initial attempt
        prompt = (
            "Schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        raw = self.llm(prompt, system=build_repair_system(), temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        last_error = None
        for attempt in range(3):  # 0 = initial, 1 = repair 1, 2 = repair 2
            if not sql:
                # If extraction failed entirely, ask the LLM to retry with a stricter hint
                repair_hint = (
                    "Your previous response did not contain a valid SQL statement. "
                    "Reply with ONLY the SQL, no prose, no markdown fences."
                )
                raw = self.llm(prompt, system=build_repair_system(repair_hint),
                               temperature=0.0, n=1)
                sql = bridge.extract_sql(raw)
                if not sql:
                    return ""

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            last_error = result.get("error", "unknown error")

            # Only two repair attempts allowed after the first failure
            if attempt >= 2:
                break

            # Feed the exact SQLite error back and ask for a corrected query
            repair_prompt = (
                "Schema:\n"
                f"{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Your previous SQL query failed to execute in SQLite with this error:\n"
                f"{last_error}\n\n"
                "The failing query was:\n"
                f"{sql}\n\n"
                "Produce a corrected SQLite-compatible SQL query that fixes the error. "
                "Output ONLY the SQL statement, with no markdown fences or commentary.\n\n"
                "SQL:"
            )
            repair_hint = (
                "Fix the SQL error reported above. Return ONLY the corrected SQL "
                "statement, with no prose or markdown fences."
            )
            raw = self.llm(repair_prompt, system=build_repair_system(repair_hint),
                           temperature=0.0, n=1)
            sql = bridge.extract_sql(raw)

        # All attempts exhausted; return the last attempted SQL (even if it failed)
        # so callers have something to inspect.
        return sql or ""