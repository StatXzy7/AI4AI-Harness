"""Generate SQL, execute it, and on failure feed the SQLite error back for up to 2 repair attempts."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS0Repair(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial generation
        prompt = (
            f"You are a SQL expert. Given the database schema below and a natural "
            f"language question, write a single, executable SQLite query that answers "
            f"the question. Return ONLY the SQL statement, with no explanation or "
            f"markdown formatting.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"SQL:"
        )
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)

        # Repair loop: up to 2 regeneration attempts on execution failure
        for _ in range(2):
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            # Execution failed: feed error back for repair
            error_msg = result.get("error", "Unknown error")
            repair_prompt = (
                f"The following SQL query was generated to answer the question, but "
                f"it failed to execute in SQLite.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Failed SQL:\n{sql}\n\n"
                f"SQLite Error:\n{error_msg}\n\n"
                f"Diagnose the cause of the error and return a corrected, executable "
                f"SQLite query. Return ONLY the corrected SQL statement, with no "
                f"explanation or markdown formatting.\n\n"
                f"SQL:"
            )
            response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)

        # Return the last candidate even if it still fails
        return sql