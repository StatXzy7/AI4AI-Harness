"""Generate SQL, execute it, and repair up to two times by feeding exact SQLite errors back to the model."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS1Repair(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are a precise Text-to-SQL assistant for SQLite. "
            "Return only one valid SQL query with no explanation."
        )

        def to_text(response) -> str:
            if response is None:
                return ""
            if isinstance(response, list):
                return str(response[0]) if response else ""
            return str(response)

        def extract_sql(text: str) -> str:
            sql = bridge.extract_sql(text)
            sql = (sql or "").strip()
            if not sql:
                sql = text.strip()
            return sql

        def execute_sql(sql: str):
            if not sql.strip():
                return False, "No SQL query was extracted from the model output."

            result = self.execute(sql)
            if not isinstance(result, dict):
                return False, "Execution result was not a dictionary."

            if result.get("ok"):
                return True, ""

            error = result.get("error", "unknown SQLite execution error")
            return False, str(error)

        base_prompt = (
            "Write a valid SQLite SQL query for the question using the schema below.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )

        last_sql = extract_sql(to_text(self.llm(base_prompt, system=system, temperature=0.0, n=1)))
        ok, error = execute_sql(last_sql)

        if ok:
            return last_sql

        for _ in range(2):
            repair_prompt = (
                "Fix the SQL query so that it executes successfully in SQLite.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Previous SQL:\n{last_sql}\n\n"
                f"SQLite execution error:\n{error}\n\n"
                "Return only the corrected SQL query."
            )

            repaired_sql = extract_sql(
                to_text(self.llm(repair_prompt, system=system, temperature=0.0, n=1))
            )

            if not repaired_sql.strip():
                error = "No SQL query was produced by the model."
                continue

            last_sql = repaired_sql
            ok, error = execute_sql(last_sql)

            if ok:
                return last_sql

        return last_sql