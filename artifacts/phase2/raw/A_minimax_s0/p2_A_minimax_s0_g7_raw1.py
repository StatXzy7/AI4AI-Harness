"""Repair mechanism: we execute the candidate SQL and feed any execution error back to the LLM for one regeneration pass."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

MAX_REPAIR_ROUNDS = 2


class P2P2AMinimaxS0G7(SQLHarness):
    def solve(self, question: str) -> str:
        base_prompt = self._build_prompt(question)

        # First attempt
        raw1 = self.llm(base_prompt, system="", temperature=0.0, n=1)
        sql1 = bridge.extract_sql(raw1)
        if not sql1:
            return ""

        result = self.execute(sql1)
        if result.get("ok"):
            return sql1

        # Repair loop: feed back execution error
        last_err = result.get("error", "unknown error")
        last_sql = sql1
        for _ in range(MAX_REPAIR_ROUNDS):
            repair_prompt = self._build_repair_prompt(question, base_prompt, last_sql, last_err)
            raw = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(raw)
            if not sql:
                break
            res = self.execute(sql)
            if res.get("ok"):
                return sql
            last_sql = sql
            last_err = res.get("error", "unknown error")

        # Repairs failed; return the most recent SQL we have (could be empty)
        return last_sql

    def _build_prompt(self, question: str) -> str:
        return (
            "You are a Text-to-SQL generator.\n"
            "Given the schema and a natural language question, produce ONE SQL query.\n"
            "Return only the SQL in a single fenced