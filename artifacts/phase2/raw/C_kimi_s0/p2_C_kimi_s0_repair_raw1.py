"""Generate SQL, execute it, and on failure feed the exact SQLite error back into the prompt to regenerate, with up to 2 repair attempts."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS0Repair(SQLHarness):
    """Execution-feedback harness: generate SQL, run it, and repair it against
    the exact SQLite error message at most MAX_REPAIRS times."""

    MAX_REPAIRS = 2

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL assistant. Given a database "
            "schema and a natural-language question, produce one correct SQLite "
            "query. Output only the SQL query, with no explanations and no "
            "markdown formatting."
        )

        context = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n"
        )

        # Step 1: initial SQL generation.
        prompt = (
            context
            + "\nWrite the single SQLite SQL query that correctly answers the question."
        )
        sql = self._generate_sql(prompt, system)

        # Step 2: execute and, on failure, feed the exact SQLite error back.
        for attempt in range(self.MAX_REPAIRS + 1):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            if attempt == self.MAX_REPAIRS:
                break

            error = result.get("error", "")
            prompt = (
                context
                + "\nA previous SQL attempt failed to execute on SQLite.\n\n"
                f"Failed SQL:\n{sql}\n\n"
                f"Exact SQLite error message:\n{error}\n\n"
                "Diagnose the cause of this exact error, fix the query, and "
                "output only the corrected SQLite SQL query."
            )
            sql = self._generate_sql(prompt, system)

        # All attempts exhausted: return the last generated SQL.
        return sql

    def _generate_sql(self, prompt: str, system: str) -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""
        return bridge.extract_sql(response)