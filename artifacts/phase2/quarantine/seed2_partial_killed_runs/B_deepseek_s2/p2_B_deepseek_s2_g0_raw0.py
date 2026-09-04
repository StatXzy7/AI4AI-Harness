"""Text-to-SQL harness that repairs generated SQL by feeding execution errors back to the LLM."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = self._build_initial_prompt(question)
        sql = bridge.extract_sql(self.llm(prompt, system="", temperature=0.0, n=1))
        last_sql = sql

        for _ in range(3):
            if not sql:
                sql = bridge.extract_sql(
                    self.llm(
                        prompt
                        + "\n\nYour previous answer did not contain SQL. Please return only the SQL query.",
                        system="",
                        temperature=0.0,
                        n=1,
                    )
                )
                if sql:
                    last_sql = sql
                else:
                    continue

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "Unknown execution error")
            repair_prompt = self._build_repair_prompt(question, sql, error)
            repaired = bridge.extract_sql(
                self.llm(repair_prompt, system="", temperature=0.0, n=1)
            )

            if repaired:
                last_sql = repaired
                sql = repaired
            else:
                # No repaired SQL produced, so further attempts would repeat the same error.
                break

        return last_sql

    def _build_initial_prompt(self, question: str) -> str:
        return (
            "You are an expert SQLite SQL generator. Given a database schema and a question, "
            "write a single SQL query that answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query, no explanation."
        )

    def _build_repair_prompt(self, question: str, sql: str, error: str) -> str:
        return (
            "You are an expert SQLite SQL generator. The following SQL query was generated for a question "
            "but produced an execution error. Fix the SQL query so that it executes successfully.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Previous SQL:\n{sql}\n\n"
            f"Error:\n{error}\n\n"
            "Return only the corrected SQL query, no explanation."
        )