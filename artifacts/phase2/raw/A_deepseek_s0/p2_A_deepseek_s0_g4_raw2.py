"""Generates SQL, executes it, and uses execution errors to repair the SQL before returning the final query."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS0G4(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQL engineer. Write a valid SQLite query for the given "
            "schema and question. Return only the SQL query."
        )
        initial_prompt = f"Schema:\n{self.schema}\n\nQuestion:\n{question}\n\nSQL:"
        sql = self._generate(initial_prompt, system)

        for _ in range(3):
            result = self.execute(sql)
            if result["ok"]:
                return sql

            error = result["error"]
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Execution error:\n{error}\n\n"
                "Please correct the SQL. Return only the corrected SQL query.\nSQL:"
            )
            sql = self._generate(repair_prompt, system)

        return sql

    def _generate(self, prompt: str, system: str) -> str:
        output = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(output, list):
            output = output[0]
        return bridge.extract_sql(output)