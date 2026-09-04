# Harness that combines a planning stage with execution-based self-repair to produce a final SQL query.
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        planning_system = (
            "You analyze a database schema and a natural language question, and you produce "
            "a concise plan describing which tables and columns are relevant and what "
            "filters, joins, and aggregations are needed. Output only the plan, no SQL."
        )
        planning_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a short plan (tables, joins, filters, aggregations) that an SQL writer "
            "can follow to answer this question."
        )
        plan = self.llm(planning_prompt, system=planning_system, temperature=0.0, n=1).strip()

        writing_system = (
            "You are an expert SQL writer. Given a schema, a question, and a plan, you "
            "produce a single SQLite-compatible SQL statement that answers the question. "
            "Output only the SQL, no commentary or markdown fences."
        )
        writing_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan}\n\n"
            "Write the final SQL query."
        )
        candidate = self.llm(writing_prompt, system=writing_system, temperature=0.0, n=1)
        sql = bridge.extract_sql(candidate)

        max_attempts = 3
        attempt = 0
        last_error = ""
        current_sql = sql
        while attempt < max_attempts:
            result = self.execute(current_sql)
            if result.get("ok"):
                return current_sql
            last_error = result.get("error", "unknown error")
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Plan:\n{plan}\n\n"
                f"Previous SQL:\n{current_sql}\n\n"
                f"Execution error:\n{last_error}\n\n"
                "Rewrite the SQL to fix the error. Output only the corrected SQL, no "
                "commentary or markdown fences."
            )
            repaired = self.llm(repair_prompt, system=writing_system, temperature=0.0, n=1)
            new_sql = bridge.extract_sql(repaired)
            if not new_sql or new_sql.strip() == current_sql.strip():
                break
            current_sql = new_sql
            attempt += 1

        return current_sql