"""Harness that generates SQL with the frozen solver, executes it, and on failure feeds the exact SQLite error back for up to 2 repair rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2Repair(SQLHarness):
    """Generate -> execute -> error-feedback repair loop (up to 2 regenerations)."""

    MAX_REPAIRS = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite text-to-SQL engine. Given a database schema "
        "and a natural-language question, write exactly one valid SQLite query "
        "that answers the question. Output only the SQL, with no explanation, "
        "no markdown fences, and no commentary."
    )

    def _generate(self, prompt: str) -> str:
        """Call the frozen solver once and extract a SQL string from its reply."""
        response = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""
        sql = bridge.extract_sql(response)
        return sql.strip() if sql else str(response).strip()

    def solve(self, question: str) -> str:
        base_context = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n"
        )

        # Step 1: initial generation.
        sql = self._generate(
            base_context
            + "\nWrite a single SQLite query that answers the question."
        )

        # Step 2: execute; on failure, feed the exact SQLite error back and
        # regenerate, up to MAX_REPAIRS times.
        for repair_round in range(self.MAX_REPAIRS + 1):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            if repair_round >= self.MAX_REPAIRS:
                break

            error = result.get("error") or "Unknown SQLite error."
            sql = self._generate(
                base_context
                + "\nThe previously generated SQL query failed to execute:\n"
                + sql
                + "\n\nThe exact SQLite error message was:\n"
                + str(error)
                + "\n\nDiagnose the cause of this error and output only the "
                  "corrected SQLite query."
            )

        # Out of repair budget: return the last candidate as-is.
        return sql