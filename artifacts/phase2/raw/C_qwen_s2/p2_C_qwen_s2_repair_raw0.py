"""Generate SQL, execute it, and repair up to two times by feeding the exact SQLite error back to the model."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite Text-to-SQL assistant. "
            "Produce only one valid SQLite SQL query. "
            "Do not include explanations or markdown."
        )

        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"SQL:"
        )

        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        raw_text = raw if isinstance(raw, str) else str(raw)
        sql = bridge.extract_sql(raw_text)
        sql = (sql or raw_text or "").strip()

        result = self.execute(sql)
        if result.get("ok"):
            return sql

        last_sql = sql
        last_error = str(result.get("error") or "unknown SQLite execution error")

        for _ in range(2):
            repair_system = (
                "You are an expert SQLite debugger. "
                "Fix the provided SQL query so that it executes successfully on SQLite. "
                "Return only the corrected SQL query."
            )

            repair_prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Previous SQL:\n{last_sql}\n\n"
                f"SQLite execution error:\n{last_error}\n\n"
                f"Corrected SQL:"
            )

            raw = self.llm(repair_prompt, system=repair_system, temperature=0.0, n=1)
            raw_text = raw if isinstance(raw, str) else str(raw)
            repaired_sql = bridge.extract_sql(raw_text)
            repaired_sql = (repaired_sql or raw_text or "").strip()

            result = self.execute(repaired_sql)
            if result.get("ok"):
                return repaired_sql

            last_sql = repaired_sql
            last_error = str(result.get("error") or last_error)

        return last_sql