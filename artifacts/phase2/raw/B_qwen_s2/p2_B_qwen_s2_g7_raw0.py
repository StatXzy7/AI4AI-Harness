"""Generate multiple SQL samples and select the first executable one, falling back by error severity."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS2G7(SQLHarness):
    def _to_sql(self, output):
        if isinstance(output, list):
            output = output[0] if output else ""
        text = str(output or "")

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = None

        sql = str(extracted or "").strip()
        if not sql:
            sql = text.strip()

        return sql

    def _execute_safe(self, sql: str):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "Unexpected execution result"}

        return result

    def solve(self, question: str) -> str:
        system = "You are an expert text-to-SQL engine. Output only one executable SQL statement."

        context = f"Schema:\n{self.schema}\n\nQuestion: {question}\n"

        prompts = [
            context + "\nReturn the SQL query that answers the question.",
            context + "\nCarefully choose the correct tables and columns, then return only the SQL query.",
            context + "\nWrite a standard SQL query with explicit join conditions where needed. Return only SQL.",
        ]

        candidates = []
        seen = set()

        for i, prompt in enumerate(prompts):
            temperature = 0.0 if i == 0 else 0.7

            try:
                response = self.llm(prompt, system=system, temperature=temperature, n=1)
            except Exception:
                continue

            sql = self._to_sql(response)
            if not sql:
                continue

            key = " ".join(sql.lower().split()).rstrip(";")
            if key in seen:
                continue

            seen.add(key)
            candidates.append(sql)

        if not candidates:
            try:
                response = self.llm(context + "\nReturn only SQL.", system=system, temperature=0.0, n=1)
            except Exception:
                return "SELECT 1"

            return self._to_sql(response) or "SELECT 1"

        fallback_sql = candidates[0]
        fallback_error_len = None

        for sql in candidates:
            result = self._execute_safe(sql)

            if result.get("ok"):
                return sql

            error = str(result.get("error") or "")
            error_len = len(error)

            if fallback_error_len is None or error_len < fallback_error_len:
                fallback_error_len = error_len
                fallback_sql = sql

        return fallback_sql