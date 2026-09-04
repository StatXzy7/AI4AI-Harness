"""Generate multiple SQL candidates and choose the best executed query."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS1G1(SQLHarness):
    def solve(self, question: str) -> str:
        prompts = self._candidate_prompts(question)
        temperatures = [0.0, 0.2, 0.5]
        system = "You are an expert SQL assistant. Return only a single SQL query."

        candidates = []
        for prompt, temperature in zip(prompts, temperatures):
            raw = self.llm(prompt, system=system, temperature=temperature, n=1)
            sql = self._extract_sql(raw)
            if sql:
                candidates.append(sql)

        if not candidates:
            raw = self.llm(prompts[0], system=system, temperature=0.0, n=1)
            sql = self._extract_sql(raw)
            if sql:
                return sql
            return raw.strip() if isinstance(raw, str) else ""

        counts = {}
        for sql in candidates:
            norm = self._normalize(sql)
            counts[norm] = counts.get(norm, 0) + 1

        best_sql = candidates[0]
        best_score = float("-inf")
        execution_cache = {}

        for sql in candidates:
            norm = self._normalize(sql)
            score = counts.get(norm, 0)

            if self._looks_like_select(sql):
                if norm not in execution_cache:
                    execution_cache[norm] = self._execute(sql)

                result = execution_cache[norm]
                if result.get("ok"):
                    score += 1000
                else:
                    score += 10
            else:
                score -= 1000

            if score > best_score:
                best_score = score
                best_sql = sql

        return best_sql

    def _candidate_prompts(self, question: str):
        return [
            (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Write one SQL query that answers the question. Output only SQL."
            ),
            (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Using only tables and columns from the schema, write the final SQL query. "
                "Output only SQL."
            ),
            (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Produce the most likely correct SQL query for this question. "
                "Do not include explanations. Output only SQL."
            ),
        ]

    def _extract_sql(self, text: str) -> str:
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)
        if not text.strip():
            return ""

        sql = bridge.extract_sql(text)
        if sql:
            return sql.strip()
        return ""

    def _normalize(self, sql: str) -> str:
        return " ".join(sql.split()).strip().rstrip(";")

    def _looks_like_select(self, sql: str) -> bool:
        text = sql.strip().lower()
        return text.startswith("select") or text.startswith("with")

    def _execute(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return result

        return {"ok": False, "rows": [], "error": "Unexpected execution result"}