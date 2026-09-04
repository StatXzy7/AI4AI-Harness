"""Generate SQL, execute it, and on failure feed the exact SQLite error back to the LLM to regenerate up to two times."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS1Repair(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        system_prompt = (
            "You are an expert SQLite query writer. Given a database schema and a question, "
            "write a single valid SQLite SQL query that answers the question. "
            "Respond with only the SQL query and no additional text."
        )

        previous_sql = ""
        previous_error = ""

        for attempt in range(3):
            if attempt == 0:
                prompt = (
                    f"Database schema:\n{schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Write the SQLite SQL query that answers the question. Output only the SQL."
                )
            else:
                prompt = (
                    f"Database schema:\n{schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Your previous SQL query:\n{previous_sql}\n\n"
                    f"That query produced the following SQLite error:\n{previous_error}\n\n"
                    f"Fix the error and write the corrected SQLite SQL query. Output only the SQL."
                )

            response = self.llm(prompt, system=system_prompt, temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            previous_sql = sql

            result = self.execute(sql)

            if result["ok"]:
                return sql

            previous_error = result.get("error", "Unknown error")

        # Return the last attempted SQL after exhausting repair attempts
        return previous_sql