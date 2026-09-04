# Repair-style harness that alternates between LLM generation and DB execution to iteratively fix SQL errors.
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G7(SQLHarness):
    """Repair: iterate generation -> execute -> feedback until success or budget exhausted."""

    MAX_REPAIRS = 3
    TEMPERATURE = 0.0

    def solve(self, question: str) -> str:
        schema = self.schema
        attempts = []
        current_sql = ""

        for repair_idx in range(self.MAX_REPAIRS + 1):
            if repair_idx == 0:
                prompt = self._build_initial_prompt(question, schema)
            else:
                prompt = self._build_repair_prompt(
                    question, schema, current_sql, attempts[-1]
                )

            system = (
                "You are an expert Text-to-SQL generator. "
                "Return ONLY a single SQL statement and nothing else."
            )
            response = self.llm(prompt, system=system, temperature=self.TEMPERATURE, n=1)
            sql = bridge.extract_sql(response)
            if not sql:
                # Couldn't parse any SQL; try once more with a stricter prompt.
                strict_prompt = (
                    prompt
                    + "\n\nIMPORTANT: Reply with ONLY the SQL statement, no markdown, no explanation."
                )
                response = self.llm(
                    strict_prompt, system=system, temperature=self.TEMPERATURE, n=1
                )
                sql = bridge.extract_sql(response)
                if not sql:
                    # Give up on this repair cycle.
                    attempts.append({"sql": "", "result": {"ok": False, "rows": [], "error": "no_sql_extracted"}})
                    continue

            result = self.execute(sql)
            attempts.append({"sql": sql, "result": result})

            if result.get("ok"):
                # Successful execution; return immediately.
                return sql

            current_sql = sql

            if repair_idx >= self.MAX_REPAIRS:
                break

        # Repair budget exhausted: return the most recent SQL candidate.
        # Prefer the one whose error message is the most "fixable" (shortest, simplest),
        # falling back to last attempted.
        best = attempts[-1]
        for entry in attempts:
            err = (entry["result"].get("error") or "").strip()
            if entry["result"].get("ok"):
                return entry["sql"]
            # Prefer entries with non-empty SQL and a recognizably "schema/syntax" error
            # over runtime ones, since those are more likely repairable in principle.
            if entry["sql"] and ("no such column" in err.lower() or "syntax error" in err.lower()):
                best = entry

        return best["sql"] if best.get("sql") else attempts[-1].get("sql", "")

    def _build_initial_prompt(self, question: str, schema: str) -> str:
        return (
            "Given the following database schema, write a single SQLite-compatible "
            "SQL query that answers the question.\n\n"
            f"SCHEMA:\n{schema}\n\n"
            f"QUESTION: {question}\n\n"
            "Return only the SQL statement (no markdown fences, no commentary)."
        )

    def _build_repair_prompt(self, question: str, schema: str, prev_sql: str, attempt: dict) -> str:
        err = (attempt["result"].get("error") or "unknown error").strip()
        rows = attempt["result"].get("rows") or []
        rows_preview = ""
        if rows:
            try:
                # Show up to 3 sample rows to help the model reground.
                rows_preview = "\nSAMPLE ROWS (up to 3):\n" + "\n".join(
                    str(r) for r in rows[:3]
                )
            except Exception:
                rows_preview = ""

        return (
            "Your previous SQL query failed when executed against the database. "
            "Carefully diagnose the error and produce a corrected SQL query.\n\n"
            f"SCHEMA:\n{schema}\n\n"
            f"QUESTION: {question}\n\n"
            f"PREVIOUS SQL:\n{prev_sql}\n\n"
            f"EXECUTION ERROR:\n{err}"
            f"{rows_preview}\n\n"
            "Return only the corrected SQL statement (no markdown fences, no commentary). "
            "Do not change the intent of the query; only fix the error."
        )