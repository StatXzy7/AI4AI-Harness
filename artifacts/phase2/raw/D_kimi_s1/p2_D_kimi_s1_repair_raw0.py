"""Generate SQL, execute it, and on failure feed the exact SQLite error back to the LLM to regenerate, up to 2 repair attempts."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1Repair(SQLHarness):
    """Text-to-SQL harness: single-shot generation, then execution-checked self-repair.

    The candidate SQL is run through self.execute(); whenever SQLite reports an
    error, the exact error message is fed back and the model is asked to fix the
    query. At most 2 repair rounds are performed; the final candidate SQL string
    is returned regardless of whether the last execution succeeded.
    """

    SYSTEM_PROMPT = (
        "You are an expert SQLite text-to-SQL assistant. Given a database "
        "schema and a natural-language question, write one correct SQLite "
        "query. Output only the SQL, with no explanation."
    )
    MAX_REPAIRS = 2

    def solve(self, question: str) -> str:
        # Step 1: initial generation.
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite query that answers the question."
        )
        sql = self._extract(
            self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        )

        # Step 2: execute; on failure, feed the exact SQLite error back and
        # regenerate, up to MAX_REPAIRS times.
        for _ in range(self.MAX_REPAIRS):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error") or "unknown SQLite error"
            repair_prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "The following SQL query failed to execute:\n"
                f"