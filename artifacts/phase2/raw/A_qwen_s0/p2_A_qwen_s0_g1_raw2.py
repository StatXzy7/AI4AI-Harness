"""Generate multiple candidate SQL statements and select the best executable candidate by vote."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        system = "You are an expert text-to-SQL system. Output only a single SQL query."

        instructions = (
            "Produce the most likely correct SQL query.",
            "Pay close attention to schema and column names; output only SQL.",
            "Use simple, executable SQL and avoid unsupported constructs.",
        )
        temperatures = (0.0, 0.2, 0.4)

        candidates = []
        for instruction, temperature in zip(instructions, temperatures):
            prompt = self._build_prompt(question, schema, instruction)
            try:
                response = self.llm(prompt, system=system, temperature=temperature, n=1)
            except Exception:
                continue

            sql = self._extract_sql(response)
            if sql:
                candidates.append(sql)

        if not candidates:
            prompt = self._build_prompt(question, schema, "Return a single SQL query.")
            try:
                response = self.llm(prompt, system=system, temperature=0.0, n=1)
            except Exception:
                return ""
            return self._extract_sql(response)

        unique_candidates = self._deduplicate(candidates)
        if not unique_candidates:
            return candidates[0]

        best_sql = None
        best_score = None

        for sql, vote_count in unique_candidates:
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            ok = 1 if isinstance(result, dict) and result.get("ok") else 0
            score = (ok, vote_count)

            if best_score is None or score > best_score:
                best_score = score
                best_sql = sql

        return best_sql or candidates[0]

    def _build_prompt(self, question: str, schema: str, instruction: str) -> str:
        return (
            f"{instruction}\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only one SQL query."
        )

    def _extract_sql(self, text: str) -> str:
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = text if isinstance(text, str) else ""

        if not isinstance(sql, str):
            return ""

        sql = sql.strip()
        while sql.endswith(";"):
            sql = sql[:-1].strip()

        return sql

    def _deduplicate(self, candidates):
        normalized = {}
        order = []

        for sql in candidates:
            key = " ".join(sql.lower().split())
            if not key:
                continue

            if key not in normalized:
                normalized[key] = [sql, 0]
                order.append(key)

            normalized[key][1] += 1

        return [(normalized[key][0], normalized[key][1]) for key in order]