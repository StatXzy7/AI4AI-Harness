"""Generate a single SQL query and repair it on execution failure using LLM-guided regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS0G2(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: initial generation
        prompt = (
            "You are an expert SQL writer. Given the schema and a natural language question, "
            "produce a single valid SQL query. Return ONLY the SQL, no explanation.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION: {question}\n\n"
            "SQL:"
        )
        raw = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)
        if not sql:
            return ""

        # Attempt execution
        result = self.execute(sql)
        if result.get("ok"):
            return sql

        # Repair loop: feed the execution error back to the LLM
        last_error = result.get("error", "Unknown execution error")
        last_sql = sql
        for attempt in range(2):
            repair_prompt = (
                "The following SQL query failed when executed against the database. "
                "Diagnose the error and produce a corrected SQL query. "
                "Return ONLY the corrected SQL, no explanation.\n\n"
                f"SCHEMA:\n{self.schema}\n\n"
                f"QUESTION: {question}\n\n"
                f"FAILED SQL:\n{last_sql}\n\n"
                f"ERROR:\n{last_error}\n\n"
                "CORRECTED SQL:"
            )
            raw2 = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql2 = bridge.extract_sql(raw2)
            if not sql2:
                break
            res2 = self.execute(sql2)
            if res2.get("ok"):
                return sql2
            last_sql = sql2
            last_error = res2.get("error", "Unknown execution error")

        # Return the most recent attempt; it is the best we have
        return last_sql