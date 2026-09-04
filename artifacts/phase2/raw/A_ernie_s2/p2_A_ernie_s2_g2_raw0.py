"""This harness uses a repair mechanism that executes generated SQL and feeds errors back to the LLM for correction."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS2G2(SQLHarness):
    def solve(self, question: str) -> str:
        # First generation attempt
        prompt = f"Given the schema: {self.schema}\nQuestion: {question}\nGenerate a SQL query."
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        result = self.execute(sql)
        if result["ok"]:
            return sql

        # Repair attempt: feed execution error back to the LLM
        error_msg = result.get("error", "Unknown error")
        repair_prompt = (
            f"Given the schema: {self.schema}\n"
            f"Question: {question}\n"
            f"The following SQL query failed with error: {error_msg}\n"
            f"SQL: {sql}\n"
            f"Generate a corrected SQL query."
        )
        repair_response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
        repaired_sql = bridge.extract_sql(repair_response)

        # Execute the repaired SQL; if it still fails, return it as the final attempt
        repaired_result = self.execute(repaired_sql)
        if repaired_result["ok"]:
            return repaired_sql
        return repaired_sql