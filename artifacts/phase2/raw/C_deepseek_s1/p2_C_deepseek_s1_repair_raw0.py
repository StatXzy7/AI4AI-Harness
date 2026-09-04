"""Generates SQL, executes it, and if it fails feeds the SQLite error back to the LLM for up to two repair attempts."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2CDeepseekS1Repair(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        initial_prompt = (
            "You are an expert SQLite SQL writer.\n"
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SELECT statement that answers the question. "
            "Return only the SQL statement, without any explanation or markdown fences."
        )

        raw = self.llm(initial_prompt, system="", temperature=0.0, n=1) or ""
        sql = bridge.extract_sql(raw) or raw.strip()

        result = self.execute(sql)
        if result.get("ok"):
            return sql

        error = result.get("error")
        if not error:
            error = "Unknown error"

        for _ in range(2):
            repair_prompt = (
                "You are an expert SQLite SQL writer.\n"
                f"Database schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                "The following SQL query was generated but produced an error when executed:\n"
                f"SQL:\n{sql}\n\n"
                f"Error:\n{error}\n\n"
                "Please fix the SQL query so it executes correctly and answers the question. "
                "Return only the corrected SQL statement, without any explanation or markdown fences."
            )

            raw = self.llm(repair_prompt, system="", temperature=0.0, n=1) or ""
            new_sql = bridge.extract_sql(raw) or raw.strip()
            if not new_sql:
                new_sql = sql

            result = self.execute(new_sql)
            if result.get("ok"):
                return new_sql

            sql = new_sql
            error = result.get("error")
            if not error:
                error = "Unknown error"

        return sql