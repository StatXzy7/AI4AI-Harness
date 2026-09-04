"""Generates SQL, executes it, and regenerates up to two times using the exact SQLite error."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS1Repair(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are a SQLite text-to-SQL engine. "
            "Return only a single executable SQLite SQL statement; no explanation or markdown."
        )

        prompt = (
            "Write a SQLite SQL query to answer the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )

        sql = self._p2p2c_generate(prompt, system)
        final_sql = sql
        result = self._p2p2c_execute(sql)

        if result.get("ok"):
            return final_sql

        for _ in range(2):
            error_value = result.get("error", "")
            error = "" if error_value is None else str(error_value)

            repair_prompt = (
                "Fix the SQLite SQL query so that it executes successfully.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Execution failed with this exact SQLite error:\n{error}\n\n"
                "Corrected SQL:"
            )

            sql = self._p2p2c_generate(repair_prompt, system)
            final_sql = sql
            result = self._p2p2c_execute(sql)

            if result.get("ok"):
                return final_sql

        return final_sql

    def _p2p2c_generate(self, prompt: str, system: str) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""

        if isinstance(response, bytes):
            response = response.decode("utf-8", errors="ignore")

        if isinstance(response, dict):
            response = (
                response.get("text")
                or response.get("content")
                or response.get("completion")
                or ""
            )

        text = str(response or "").strip()
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            return text

        return str(extracted or "").strip()

    def _p2p2c_execute(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": f"{type(exc).__name__}: {exc}"}

        if isinstance(result, dict):
            return result

        return {"ok": bool(result), "rows": [], "error": "" if result else "execution failed"}