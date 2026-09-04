"""Generates a SQL query and repairs it by feeding execution errors back into a second generation."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS1G7(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are a SQL expert. Output only a SQL query without explanation."

        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n"
            "Write a SQLite SELECT query that answers the question."
        )
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(response) or self._raw_text(response)

        for _ in range(2):
            if not sql:
                break
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            error = result.get("error") or "Unknown error"
            repair_prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Previous SQL:\n{sql}\n"
                f"Error:\n{error}\n\n"
                "Write a corrected SQLite SELECT query."
            )
            response = self.llm(repair_prompt, system=system, temperature=0.0, n=1)
            sql = bridge.extract_sql(response) or self._raw_text(response)

        return sql if sql else ""

    @staticmethod
    def _raw_text(response) -> str:
        if isinstance(response, list) and response:
            response = response[0]
        if isinstance(response, dict):
            if "text" in response:
                response = response["text"]
            elif "choices" in response and response["choices"]:
                choice = response["choices"][0]
                if isinstance(choice, dict):
                    response = choice.get("text", "")
                else:
                    response = str(choice)
        return str(response or "").strip()