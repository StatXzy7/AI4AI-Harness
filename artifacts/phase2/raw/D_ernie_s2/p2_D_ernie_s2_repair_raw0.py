"""Generate SQL via frozen LLM, execute it, and repair on failure by feeding the SQLite error back up to two retries."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Solve a Text-to-SQL question by generating SQL with a frozen weak solver,
        executing it, and repairing on failure by feeding the exact SQLite error
        back into the LLM for up to 2 retries.
        """
        max_attempts = 3  # initial + 2 retries
        last_error = None

        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nGenerate a valid SQLite SQL query to answer the question."
            else:
                prompt = (
                    f"The following SQL query failed with this SQLite error:\n\n{last_error}\n\n"
                    f"Original question: {question}\n\n"
                    f"Database schema:\n\n{self.schema}\n\n"
                    f"Please generate a corrected SQLite SQL query that addresses the error."
                )

            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql_text = bridge.extract_sql(response)

            result = self.execute(sql_text)
            if result["ok"]:
                return sql_text

            last_error = result.get("error", "Unknown execution error")

        # If all attempts failed, return the last generated SQL anyway
        return sql_text