"""Sample multiple SQL candidates and choose the best one using execution results."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        system = (
            "You are an expert Text-to-SQL system. "
            "Return only one SQL query. No explanations and no markdown."
        )
        base_prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL query that answers the question."
        )

        prompts = [
            base_prompt,
            base_prompt + "\n\nCheck every table and column name against the schema before answering.",
            base_prompt + "\n\nPrefer simple, standard SQL. If joins are needed, use explicit join conditions.",
        ]

        candidates = []
        for i, prompt in enumerate(prompts):
            temperature = 0.0 if i == 0 else 0.2 + 0.2 * i
            try:
                raw = self.llm(prompt, system=system, temperature=temperature, n=1)
            except Exception:
                raw = ""

            sql = self._extract_sql(raw)
            if sql:
                candidates.append(sql)

        if not candidates:
            try:
                raw = self.llm(base_prompt, system=system, temperature=0.0, n=1)
            except Exception:
                raw = ""
            return self._extract_sql(raw)

        frequencies = {}
        for sql in candidates:
            key = self._normalize(sql)
            frequencies[key] = frequencies.get(key, 0) + 1

        best_sql = candidates[0]
        best_rank = None

        for idx, sql in enumerate(candidates):
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            ok = bool(result.get("ok", False))
            rank = (
                0 if ok else 1,
                -frequencies.get(self._normalize(sql), 0),
                idx,
            )

            if best_rank is None or rank < best_rank:
                best_rank = rank
                best_sql = sql

        return best_sql

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        if extracted:
            return str(extracted).strip()

        return str(text).strip().strip("`").strip()

    def _normalize(self, sql: str) -> str:
        return " ".join(str(sql).lower().split()).rstrip(";")