"""Iteratively generates multiple SQL candidates and repairs them with execution feedback until one executes successfully."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G3(SQLHarness):
    def _call_llm(self, prompt: str, system: str, temperature: float = 0.0) -> str:
        raw = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        return raw or ""

    def _extract_sql(self, raw: str) -> str:
        if not raw:
            return ""
        try:
            sql = bridge.extract_sql(raw)
        except Exception:
            sql = raw.strip()
        return sql.strip() if sql else raw.strip()

    def solve(self, question: str) -> str:
        schema = self.schema or ""
        system = "You are a careful text-to-SQL assistant. Return only SQL."

        base_prompt = (
            f"Given the database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query that answers the question. Do not explain."
        )

        # 1) Generate several independent candidates.
        candidates = []
        for i in range(3):
            try:
                raw = self._call_llm(
                    base_prompt,
                    system=system,
                    temperature=0.3 if i > 0 else 0.0,
                )
                sql = self._extract_sql(raw)
                if sql:
                    candidates.append(sql)
            except Exception:
                continue

        if not candidates:
            try:
                raw = self._call_llm(base_prompt, system=system, temperature=0.0)
                sql = self._extract_sql(raw)
                candidates.append(sql or raw.strip())
            except Exception:
                return ""

        # 2) Try each candidate against the actual database, remembering the last failure.
        last_error = ""
        for sql in candidates:
            try:
                result = self.execute(sql)
                if result.get("ok"):
                    return sql
                last_error = result.get("error", "")
            except Exception as exc:
                last_error = str(exc)

        current_sql = candidates[-1]

        # 3) Execution-guided repair loop.
        for _ in range(3):
            if last_error:
                feedback = (
                    f"\n\nPrevious SQL:\n{current_sql}\n"
                    f"Execution error:\n{last_error}\n"
                    "Please return only the corrected SQL query."
                )
            else:
                feedback = (
                    f"\n\nPrevious SQL:\n{current_sql}\n"
                    "Please return a corrected SQL query."
                )

            try:
                raw = self._call_llm(base_prompt + feedback, system=system, temperature=0.0)
                sql = self._extract_sql(raw)
            except Exception:
                continue

            if not sql:
                continue

            current_sql = sql
            try:
                result = self.execute(current_sql)
                if result.get("ok"):
                    return current_sql
                last_error = result.get("error", "")
            except Exception as exc:
                last_error = str(exc)

        return current_sql