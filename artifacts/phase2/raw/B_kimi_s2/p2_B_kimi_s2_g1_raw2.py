"""Text-to-SQL harness that executes candidate SQL and feeds execution errors back into a bounded repair loop until a query runs successfully."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G1(SQLHarness):
    """Improvement over a single greedy call: a bounded execute-and-repair loop.

    Instead of returning the first generated query, the harness executes it
    against the database. If execution fails, the failing SQL and the exact
    database error message are appended to the prompt and the frozen solver is
    asked to produce a corrected query. The loop stops as soon as a query
    executes successfully or the attempt budget is exhausted, in which case the
    last candidate is returned.
    """

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite SQL generator. Given a database schema "
            "and a natural-language question, you produce exactly one valid "
            "SQLite query that answers the question. Output only the SQL, "
            "with no explanations and no markdown fences."
        )

        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SQL query that answers the question."
        )

        repair_context = ""
        last_sql = ""

        for _attempt in range(self.MAX_ATTEMPTS):
            prompt = base_prompt + repair_context

            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""

            sql = bridge.extract_sql(raw)
            if not sql:
                sql = str(raw).strip()
            if not sql:
                # Nothing usable came back; nudge the solver rather than executing junk.
                repair_context += (
                    "\n\nYour previous reply contained no SQL query. "
                    "Respond with exactly one SQLite SQL query and nothing else."
                )
                continue

            last_sql = sql
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            error = result.get("error") or "unknown execution error"
            repair_context += (
                f"\n\nYour previous SQL query was:\n{sql}\n\n"
                f"When executed, it failed with this database error:\n{error}\n\n"
                "Diagnose the cause, check every table and column name against "
                "the schema above, and output one corrected SQLite SQL query. "
                "Output only the corrected SQL."
            )

        # Budget exhausted: return the most recent candidate rather than nothing.
        return last_sql