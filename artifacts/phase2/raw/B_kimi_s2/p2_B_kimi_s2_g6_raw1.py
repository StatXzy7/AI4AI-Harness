"""Repair-loop harness: generate SQL greedily, execute it, and feed execution errors back to the LLM for regeneration until the query runs or attempts run out."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G6(SQLHarness):
    """Generate -> execute -> on error, re-prompt with the error trace -> repeat."""

    MAX_ATTEMPTS = 4

    def _build_base_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SELECT query that answers the question. "
            "Output ONLY the SQL, with no explanation and no markdown fences."
        )

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL engine for SQLite. "
            "You output exactly one syntactically valid SQLite query and nothing else."
        )

        base_prompt = self._build_base_prompt(question)
        prompt = base_prompt
        last_sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            # Greedy on the first try; slight temperature on retries so the
            # model can escape a repeated failure mode.
            temperature = 0.0 if attempt == 0 else 0.4
            text = self.llm(prompt, system=system, temperature=temperature, n=1)
            sql = bridge.extract_sql(text)

            if not sql:
                # Nothing parseable came back: ask again with a stricter reminder.
                prompt = (
                    base_prompt
                    + "\n\nYour previous reply could not be parsed as a SQL query. "
                    "Respond with ONLY the raw SQL text, nothing else."
                )
                continue

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            last_sql = sql
            error = result.get("error", "unknown execution error")
            prompt = (
                base_prompt
                + "\n\nA previous attempt produced this SQL:\n"
                + sql
                + "\n\nIt failed to execute with this SQLite error:\n"
                + str(error)
                + "\n\nDiagnose the cause (check table names, column names, "
                "join keys, and aggregation against the schema) and output ONLY "
                "the corrected SQLite query."
            )

        # All attempts failed: return the best-effort candidate so the caller
        # still receives a SQL string.
        if last_sql:
            return last_sql
        return bridge.extract_sql(
            self.llm(base_prompt, system=system, temperature=0.0, n=1)
        )