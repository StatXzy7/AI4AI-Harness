"""Repair mechanism: execute the generated SQL and use execution errors to regenerate a corrected query."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question, self.schema)
        sql = bridge.extract_sql(self.llm(prompt, system="", temperature=0.0, n=1))

        for _ in range(3):
            result = self.execute(sql)
            if result["ok"]:
                return sql

            error = result.get("error", "unknown execution error")
            repair_prompt = self._build_repair_prompt(question, sql, error, self.schema)
            new_sql = bridge.extract_sql(
                self.llm(repair_prompt, system="", temperature=0.0, n=1)
            )

            if new_sql.strip() == sql.strip():
                break

            sql = new_sql

        return sql

    @staticmethod
    def _build_prompt(question: str, schema: str) -> str:
        return (
            f"Given the following database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query to answer the question. Output only SQL."
        )

    @staticmethod
    def _build_repair_prompt(question: str, sql: str, error: str, schema: str) -> str:
        return (
            f"Given the following database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            f"The following SQL query was generated but failed to execute:\n{sql}\n\n"
            f"Error:\n{error}\n\n"
            "Please correct the SQL query. Output only SQL."
        )