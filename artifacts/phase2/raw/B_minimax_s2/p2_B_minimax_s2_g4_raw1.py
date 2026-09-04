# Single-pass generation: produce an initial draft, validate via execution, then iteratively repair using error feedback.
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        draft_prompt = (
            "You are an expert SQLite engineer. Given the schema and the user's "
            "question, write exactly one valid SQL query that answers it. "
            "Output only the SQL statement, no commentary, no markdown fences.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )

        raw = self.llm(draft_prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)
        if not sql:
            return ""

        max_repairs = 3
        for attempt in range(max_repairs):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            err = result.get("error") or "unknown execution error"
            repair_prompt = (
                "The following SQL produced an execution error. Fix it so it runs "
                "correctly against SQLite. Output only the corrected SQL statement, "
                "no commentary, no markdown fences.\n\n"
                f"Original SQL:\n{sql}\n\n"
                f"Error:\n{err}\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Corrected SQL:"
            )
            raw_repair = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            repaired = bridge.extract_sql(raw_repair)
            if not repaired or repaired.strip() == sql.strip():
                break
            sql = repaired

        return sql