"""Generate SQL with the frozen LLM, execute it, and on failure feed the exact SQLite error back for up to two repair regenerations."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2Repair(SQLHarness):
    """Execute-then-repair harness: generate SQL, run it, and regenerate with the exact SQLite error up to 2 times."""

    MAX_REPAIRS = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite SQL generator. Given a database schema and a "
        "natural-language question, produce exactly one valid SQLite query that "
        "answers the question. Output only the SQL, with no explanations and no "
        "markdown formatting."
    )

    def solve(self, question: str) -> str:
        """Generate SQL, execute it, and repair up to MAX_REPAIRS times using the exact SQLite error."""
        base_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SQL query that answers the question."
        )

        sql = ""
        error = ""

        for attempt in range(self.MAX_REPAIRS + 1):
            if attempt == 0:
                prompt = base_prompt
            else:
                prompt = (
                    f"Database schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    "Your previous SQL query failed to execute on the database.\n\n"
                    f"Failed SQL:\n{sql}\n\n"
                    f"Exact SQLite error message:\n{error}\n\n"
                    "Diagnose the cause of this exact error and output a corrected "
                    "single SQLite SQL query. Output only the corrected SQL."
                )

            response = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
            if isinstance(response, (list, tuple)):
                response = response[0] if response else ""

            sql = bridge.extract_sql(str(response))
            if not sql:
                error = "No SQL statement could be extracted from the model response."
                continue

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error") or "Unknown SQLite execution error."

        return sql