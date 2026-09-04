"""Generate SQL with the frozen solver, execute it, and on failure feed the exact SQLite error back for up to 2 regeneration rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2Repair(SQLHarness):
    """Execution-checked Text-to-SQL harness: generate, execute, and repair via exact-error feedback (max 2 repairs)."""

    MAX_REPAIRS = 2

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL solver for SQLite. "
            "Given a database schema and a natural-language question, output exactly one "
            "valid SQLite SQL query that answers the question. Output only the SQL, "
            "with no explanations or commentary."
        )

        # Step 1: initial SQL generation.
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SQL query that answers the question."
        )
        sql = self._generate(prompt, system, fallback="")

        # Step 2: execute; on failure, feed the exact SQLite error back and regenerate (up to MAX_REPAIRS times).
        for repair_round in range(self.MAX_REPAIRS + 1):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            if repair_round == self.MAX_REPAIRS:
                break  # repairs exhausted; return the last candidate below

            error = result.get("error") or "unknown SQLite error"
            repair_prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"The following SQL query failed to execute:\n