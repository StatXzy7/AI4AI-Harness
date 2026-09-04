"""Generate SQL, execute it, and repair it using execution errors."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BDeepseekS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        system = (
            "You are an expert SQLite engineer. Given a database schema and a "
            "natural language question, write a single SQLite SQL query. "
            "Output only SQL, no explanation."
        )

        prompt = f"Schema:\n{schema}\n\nQuestion:\n{question}\n\nSQL:"

        last_sql = ""

        for attempt in range(3):
            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            raw_text = str(raw).strip()

            sql = bridge.extract_sql(raw_text) or raw_text
            last_sql = sql

            if not sql:
                prompt = (
                    f"Your previous response was empty. Write a SQL query for "
                    f"the schema and question.\n\nSchema:\n{schema}\n\n"
                    f"Question:\n{question}\n\nSQL:"
                )
                system = "You are a SQLite expert. Output only SQL."
                continue

            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if isinstance(result, dict) and result.get("ok"):
                return sql

            error = (
                result.get("error", "unknown error")
                if isinstance(result, dict)
                else str(result)
            )

            prompt = (
                f"The following SQLite query failed:\n{sql}\n\n"
                f"Database error:\n{error}\n\n"
                f"Schema:\n{schema}\n\n"
                f"Question:\n{question}\n\n"
                "Write a corrected SQLite query based on the error. Output only SQL."
            )
            system = (
                "You are a SQLite expert. Fix the SQL query based on the "
                "execution error. Output only SQL."
            )

        return last_sql or ""