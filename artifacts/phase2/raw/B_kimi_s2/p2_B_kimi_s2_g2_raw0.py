"""Execution-feedback repair harness: generate SQL, execute it, and feed database errors back into iterative regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G2(SQLHarness):
    """Repair loop harness.

    Improvement over single greedy generation: instead of returning the
    first decoded SQL string, the harness executes it against the database.
    If execution fails, the faulty SQL and the database's error message are
    appended to the prompt and the model is asked to produce a corrected
    query. The loop repeats until a query executes successfully or the
    attempt budget is exhausted, in which case the most recent candidate is
    returned as a best effort.
    """

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL engine for SQLite databases. "
            "You write exactly one correct SQLite query per answer. "
            "You output only SQL: no explanations, no comments, no markdown fences."
        )
        base_prompt = (
            "You are given a database schema and a question.\n\n"
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite query that answers the question. "
            "Use only tables and columns that appear in the schema. Output only the SQL."
        )

        prompt = base_prompt
        last_sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            # Greedy first try; slight diversity on retries to escape repeated mistakes.
            temperature = 0.0 if attempt == 0 else 0.4
            raw = self.llm(prompt, system=system, temperature=temperature)
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""

            sql = self._to_sql(str(raw))
            if not sql:
                prompt = (
                    base_prompt
                    + "\n\nYour previous reply contained no SQL. "
                      "Reply with exactly one SQLite query and nothing else."
                )
                continue

            last_sql = sql
            outcome = self.execute(sql)

            if outcome.get("ok"):
                return sql

            error = str(outcome.get("error", "unknown execution error"))
            prompt = (
                f"{base_prompt}\n\n"
                "A previous attempt produced SQL that failed to execute.\n"
                f"Faulty SQL:\n{sql}\n\n"
                f"The database returned this error:\n{error}\n\n"
                "Diagnose the cause: verify every table and column name against the "
                "schema, check JOIN keys, quote string literals, and fix any syntax "
                "problem. Then output only the corrected SQLite query."
            )

        return last_sql or "SELECT 1"

    def _to_sql(self, raw_text: str) -> str:
        """Extract SQL from model output, with a markdown-fence fallback."""
        sql = bridge.extract_sql(raw_text)
        if sql and sql.strip():
            return sql.strip()
        text = raw_text.strip()
        if text.startswith("