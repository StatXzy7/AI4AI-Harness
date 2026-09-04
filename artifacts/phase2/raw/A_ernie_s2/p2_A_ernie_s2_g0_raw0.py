"""Uses iterative SQL repair: executes generated SQL and feeds execution errors back to the LLM for correction."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL from question and schema
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nAnswer the following question with a SQL query:\n{question}"
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)

        # Execute the generated SQL
        result = self.execute(sql)

        # If execution fails, attempt repair with error feedback
        if not result["ok"]:
            repair_prompt = f"Given the following database schema:\n\n{self.schema}\n\nOriginal question:\n{question}\n\nThe following SQL query was generated but produced an error:\n{sql}\n\nError message: {result['error']}\n\nPlease generate a corrected SQL query that fixes the error."
            repair_response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(repair_response)

        return sql