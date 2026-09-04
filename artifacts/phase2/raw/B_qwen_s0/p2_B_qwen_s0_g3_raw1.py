"""Generate SQL, execute it, and repair it using execution errors."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        max_repairs = 3
        system = "You are an expert SQL assistant. Respond only with a single valid SQLite SQL query."

        def as_text(value) -> str:
            if isinstance(value, (list, tuple)):
                return str(value[0]) if value else ""
            return str(value or "")

        def extract_sql(text: str) -> str:
            extracted = bridge.extract_sql(text)
            return str(extracted or text or "").strip()

        initial_prompt = (
            "Write a SQLite SQL query that answers the question.\n"
            "Use only the tables and columns shown in the schema.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL only:"
        )

        raw = as_text(self.llm(initial_prompt, system=system, temperature=0.0, n=1))
        sql = extract_sql(raw)
        last_error = "No SQL was produced."

        for attempt in range(max_repairs + 1):
            if sql:
                try:
                    result = self.execute(sql)
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                else:
                    if isinstance(result, dict) and result.get("ok"):
                        return sql
                    if isinstance(result, dict):
                        last_error = str(result.get("error") or "Execution failed.").strip()
                    else:
                        last_error = str(result or "Execution failed.").strip()
            else:
                last_error = "No SQL was produced."

            if attempt == max_repairs:
                break

            repair_prompt = (
                "The following SQL query failed.\n"
                "Repair it so it is valid SQLite and answers the question.\n"
                "Use only the provided schema.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Previous SQL:\n{sql or '(no SQL)'}\n\n"
                f"Execution error:\n{last_error[:1000]}\n\n"
                "Return only the corrected SQL query:"
            )

            raw = as_text(self.llm(repair_prompt, system=system, temperature=0.0, n=1))
            repaired = extract_sql(raw)

            if not repaired:
                sql = ""
                last_error = "The repair response contained no SQL."
            elif repaired == sql:
                sql = repaired
                break
            else:
                sql = repaired

        return sql