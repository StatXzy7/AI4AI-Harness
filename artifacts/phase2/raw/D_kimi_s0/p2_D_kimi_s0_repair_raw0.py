"""Generate SQL from the frozen LLM, execute it, and on failure feed the exact SQLite error back to regenerate up to 2 times."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS0Repair(SQLHarness):
    """Zero-shot Text-to-SQL with execution-guided self-repair.

    The frozen solver generates an initial SQL query from the schema and the
    question. The harness executes that query; if SQLite reports an error, the
    exact error message (plus the failing SQL, schema, and question) is fed
    back to the frozen LLM, which regenerates a corrected query. This repair
    loop repeats at most MAX_REPAIRS times, after which the most recently
    generated SQL string is returned regardless of its execution status.
    """

    MAX_REPAIRS = 2

    def _generate_prompt(self, question: str) -> str:
        return (
            "You are an expert SQLite SQL generator.\n"
            "Given the database schema and a natural-language question, write a "
            "single valid SQLite query that answers the question.\n\n"
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Respond with only the SQL query. No explanation, no markdown fences."
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            "You are an expert SQLite SQL generator.\n"
            "Your previous SQL query failed to execute against the database. "
            "Fix it using the exact SQLite error message below.\n\n"
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Previous (failing) SQL:\n"
            f"{bad_sql}\n\n"
            "Exact SQLite error:\n"
            f"{error}\n\n"
            "Respond with only the corrected SQL query. No explanation, no "
            "markdown fences."
        )

    def solve(self, question: str) -> str:
        # Step 1: initial zero-shot generation from the frozen solver.
        sql = bridge.extract_sql(
            self.llm(
                self._generate_prompt(question),
                system="",
                temperature=0.0,
                n=1,
            )
        )

        # Step 2: execute; on failure, feed the exact SQLite error back and
        # regenerate, up to MAX_REPAIRS times.
        for _repair_attempt in range(self.MAX_REPAIRS):
            result = self.execute(sql)
            if result.get("ok"):
                break

            exact_error = result.get("error", "") or "Unknown SQLite error."
            sql = bridge.extract_sql(
                self.llm(
                    self._repair_prompt(question, sql, exact_error),
                    system="",
                    temperature=0.0,
                    n=1,
                )
            )

        return sql