"""Draw multiple SQL samples and select the best executable candidate."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2AQwenS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        prompt = self._sql_prompt(question, schema)
        system = "You are a precise text-to-SQL assistant. Return only one SQL statement."

        candidates = []
        seen = set()

        for temperature in (0.0, 0.4, 0.7):
            raw = self._call_llm(prompt, system=system, temperature=temperature)
            sql = self._extract_sql(raw)
            if not sql:
                continue

            sql = self._normalize_sql(sql)
            key = self._sql_key(sql)
            if key in seen:
                continue

            seen.add(key)
            result = self._execute_sql(sql)
            candidates.append(
                {
                    "sql": sql,
                    "ok": result["ok"],
                    "error": result["error"],
                }
            )

        if not candidates:
            return "SELECT 1"

        executable = [c for c in candidates if c["ok"]]
        pool = executable if executable else candidates

        if len(pool) > 1:
            chosen = self._select_best(question, schema, pool)
            if chosen:
                return chosen

        if executable:
            return executable[0]["sql"]

        candidates.sort(key=lambda c: len(c.get("error", "")))
        return candidates[0]["sql"]

    def _sql_prompt(self, question: str, schema: str) -> str:
        return (
            "Write a single SQL query that answers the question.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only the SQL query, without explanation."
        )

    def _call_llm(self, prompt: str, system: str = "", temperature: float = 0.0, n: int = 1) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=n)
        except TypeError:
            try:
                response = self.llm(prompt, system=system)
            except Exception:
                return ""
        except Exception:
            return ""

        if isinstance(response, list):
            return str(response[0]) if response else ""
        return "" if response is None else str(response)

    def _extract_sql(self, text: str) -> str:
        if text is None:
            return ""

        text = str(text)
        try:
            extracted = bridge.extract_sql(text)
            if extracted:
                return str(extracted)
        except Exception:
            pass

        return self._fallback_extract_sql(text)

    def _fallback_extract_sql(self, text: str) -> str:
        if not text:
            return ""

        fenced = re.findall(r"