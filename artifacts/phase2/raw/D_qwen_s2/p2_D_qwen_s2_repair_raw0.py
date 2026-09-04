"""Generates SQL, executes it, and repairs up to two times using the exact SQLite error."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS2Repair(SQLHarness):
    def _llm_text(self, prompt: str, system: str) -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)

        if response is None:
            return ""

        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""

        if response is None:
            return ""

        return str(response)

    def _extract_sql(self, text: str) -> str:
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        if not isinstance(sql, str):
            sql = str(sql or "")

        sql = sql.strip()

        if not sql:
            sql = text.strip()

        return sql

    def _execute_sql(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if not isinstance(result, dict):
            return {
                "ok": False,
                "rows": [],
                "error": "Execution result was not a dictionary.",
            }

        return result

    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""

        system = (
            "You are an expert SQLite SQL engineer. "
            "Return only a single executable SQL query, with no explanation."
        )

        task_context = (
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n"
        )

        initial_prompt = (
            task_context
            + "\nGenerate a SQLite SQL query that answers the question. "
            "Return only SQL."
        )

        response = self._llm_text(initial_prompt, system)
        sql = self._extract_sql(response)
        last_sql = sql

        execution = self._execute_sql(sql)

        if execution.get("ok"):
            return last_sql

        last_error = str(execution.get("error") or "Unknown SQLite execution error.")

        for _ in range(2):
            repair_prompt = (
                task_context
                + "\nThe previous SQL failed when executed in SQLite.\n\n"
                + f"Previous SQL:\n{last_sql}\n\n"
                + f"Exact SQLite error:\n{last_error}\n\n"
                + "Fix the SQL so it executes correctly and answers the question. "
                + "Return only SQL."
            )

            response = self._llm_text(repair_prompt, system)
            candidate_sql = self._extract_sql(response)

            if candidate_sql:
                last_sql = candidate_sql

            execution = self._execute_sql(candidate_sql)

            if execution.get("ok"):
                return candidate_sql

            last_error = str(execution.get("error") or "Unknown SQLite execution error.")

        return last_sql