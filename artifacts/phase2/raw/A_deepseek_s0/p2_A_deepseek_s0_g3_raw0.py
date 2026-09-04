"""Generate SQL and repair it by feeding execution errors back into the LLM."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS0G3(SQLHarness):
    def _generate_sql(self, prompt: str, system: str) -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, list):
            response = response[0] if response else ""
        if response is None:
            response = ""
        return bridge.extract_sql(response) or ""

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQL engineer. Write SQL queries for the provided question "
            "using the schema below. Return only the SQL query without any markdown fences."
            f"\n\nSchema:\n{self.schema}"
        )
        prompt = f"Question: {question}\nReturn the SQL query:"

        sql = self._generate_sql(prompt, system)
        result = self.execute(sql)

        if (result or {}).get("ok"):
            return sql

        previous_sql = sql
        for _ in range(2):
            error = (result or {}).get("error", "Unknown execution error")
            repair_prompt = (
                f"Question: {question}\n\n"
                f"Your previous SQL query failed to execute:\n{previous_sql or '(empty)'}\n\n"
                f"Execution error:\n{error}\n\n"
                "Write a corrected SQL query. Return only SQL, no explanation."
            )

            candidate = self._generate_sql(repair_prompt, system)
            if not candidate:
                continue

            previous_sql = candidate
            result = self.execute(previous_sql)

            if (result or {}).get("ok"):
                return previous_sql

        return previous_sql or sql or "SELECT 1"