"""Self-repairing Text-to-SQL harness: generates SQL, executes it, and feeds back SQLite errors for up to 2 regenerations."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial system prompt
        system_prompt = (
            "You are an expert SQLite SQL generator. "
            "Given a database schema and a natural language question, "
            "produce a single valid SQLite query that answers the question. "
            "Return ONLY the SQL statement, with no explanation, no markdown, and no code fences."
        )

        # First attempt
        user_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query."
        )
        response = self.llm(user_prompt, system=system_prompt, temperature=0.0, n=1)
        sql = bridge.extract_sql(response)

        # Up to 2 repair iterations on execution failure
        for _ in range(2):
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            error_msg = result.get("error", "Unknown error")
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Your previous SQL was:\n{sql}\n\n"
                f"It produced this SQLite error:\n{error_msg}\n\n"
                "Return a corrected SQL query that fixes the error. "
                "Return ONLY the SQL statement, with no explanation or markdown."
            )
            response = self.llm(repair_prompt, system=system_prompt, temperature=0.0, n=1)
            sql = bridge.extract_sql(response)

        # Final attempt: return the last SQL even if it still fails
        return sql