"""Execution-feedback repair harness: generate SQL, run it, and feed the database error back for bounded regeneration until the query executes."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G7(SQLHarness):
    """Generate SQL, execute it, and feed SQLite errors back into the prompt for a
    bounded number of repair rounds, returning the first query that runs."""

    MAX_ROUNDS = 4

    SYSTEM = (
        "You are an expert SQLite text-to-SQL engine. Given a database schema and a "
        "natural-language question, you produce exactly one valid SQLite SELECT query. "
        "Output only the SQL text: no explanation, no comments, no markdown fences."
    )

    def solve(self, question: str) -> str:
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite SELECT query that answers the question. Output only the SQL."
        )

        prompt = base_prompt
        last_sql = ""

        for round_idx in range(self.MAX_ROUNDS):
            # First attempt is greedy; repair attempts get mild sampling noise so the
            # model does not deterministically repeat the identical failing query.
            temperature = 0.0 if round_idx == 0 else 0.4
            raw = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""

            sql = bridge.extract_sql(raw)

            if not sql:
                # Nothing parseable came back: tighten the instruction and retry.
                prompt = (
                    f"{base_prompt}\n\n"
                    "Your previous reply contained no SQL query. Respond with exactly "
                    "one SQLite SELECT statement and nothing else."
                )
                continue

            last_sql = sql

            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive: treat harness-level crashes as errors
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                return sql

            error = (result.get("error") or "unknown error").strip()
            if len(error) > 500:
                error = error[:500]

            prompt = (
                f"{base_prompt}\n\n"
                "Your previous query failed to execute.\n"
                f"Failing SQL:\n{sql}\n"
                f"SQLite error message:\n{error}\n\n"
                "Repair the query. Verify that every table and column you reference "
                "exists in the schema above, that string literals are single-quoted, "
                "and that the syntax is valid SQLite. Output only the corrected SQL."
            )

        # Repair budget exhausted: return the last candidate rather than an empty string.
        return last_sql