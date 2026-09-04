"""A Text-to-SQL harness that repairs its SQL by executing each candidate and feeding the database error back to the LLM for bounded regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G4(SQLHarness):
    """Generate SQL, execute it, and loop the error back into the model on failure."""

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL assistant. Given a database "
            "schema and a natural-language question, you output exactly one "
            "valid SQLite SELECT query. Output only the SQL: no explanation, "
            "no markdown fences, no comments."
        )
        base_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite SELECT query that answers the question."
        )

        feedback = ""
        sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            # Stay greedy on the first try; add slight diversity on retries so
            # the model can escape whatever mistake caused the failure.
            temperature = 0.0 if attempt == 0 else 0.3
            raw = self.llm(
                base_prompt + feedback,
                system=system,
                temperature=temperature,
                n=1,
            )
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""

            sql = bridge.extract_sql(raw) or (raw or "").strip()

            if not sql:
                feedback += (
                    "\n\nYour previous reply contained no SQL query. "
                    "Respond with only the SQL query."
                )
                continue

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = str(result.get("error", "unknown error"))[:500]
            feedback += (
                f"\n\nYour previous SQL:\n{sql}\n"
                f"failed when executed with this SQLite error:\n{error}\n"
                "Diagnose the cause (check table/column names against the "
                "schema, join keys, aggregate usage, and syntax) and output "
                "only the corrected SQL query."
            )

        # All attempts failed: return the last candidate as a best effort.
        return sql