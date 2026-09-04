"""Generate SQL, execute it, and use execution errors to repair the query."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G1(SQLHarness):
    MAX_REPAIRS = 3

    def solve(self, question: str) -> str:
        system = (
            "You are a text-to-SQL assistant. Given a database schema and a question, "
            "output only the SQL query, with no extra explanation."
        )
        prompt = self._build_initial_prompt(question)
        sql = self._generate_sql(prompt, system)

        for _ in range(self.MAX_REPAIRS):
            if not sql:
                error = "Your previous answer did not contain a SQL query."
            else:
                result = self.execute(sql)
                if result.get("ok"):
                    return sql
                error = result.get("error") or "Unknown execution error."

            prompt = self._build_repair_prompt(question, sql, error)
            sql = self._generate_sql(prompt, system)

        if sql:
            result = self.execute(sql)
            if result.get("ok"):
                return sql
        return sql or ""

    def _build_initial_prompt(self, question: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the correct SQL query."
        )

    def _build_repair_prompt(self, question: str, sql: str, error: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Your previous SQL was:\n{sql or '<none>'}\n\n"
            f"Execution error:\n{error}\n\n"
            "Please correct the SQL query. Output only the corrected SQL query."
        )

    def _generate_sql(self, prompt: str, system: str) -> str:
        output = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(output, list):
            output = output[0] if output else ""
        if isinstance(output, dict):
            output = output.get("text") or output.get("content") or ""
        text = output if isinstance(output, str) else str(output)
        return bridge.extract_sql(text).strip()