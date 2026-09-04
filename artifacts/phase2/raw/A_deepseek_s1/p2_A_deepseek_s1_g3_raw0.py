"""Execute generated SQL, then repair it using execution error messages fed back to the LLM."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS1G3(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        system = "You are an expert SQL writer. Respond with SQL only."
        max_attempts = 3

        prompt = (
            "You are an expert SQL writer. Given a database schema and a question, "
            "write a correct SQL query.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query."
        )
        sql = bridge.extract_sql(self.llm(prompt, system=system, temperature=0.0, n=1))

        for _ in range(max_attempts):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "unknown error")
            repair_prompt = (
                "You are an expert SQL writer. The following SQL query produced an error. "
                "Write a corrected SQL query based on the schema and question.\n\n"
                f"Schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Error:\n{error}\n\n"
                "Return only the corrected SQL query."
            )
            sql = bridge.extract_sql(
                self.llm(repair_prompt, system=system, temperature=0.0, n=1)
            )

        return sql