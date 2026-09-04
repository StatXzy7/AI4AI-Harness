"""Samples multiple SQL candidates and selects the best one by executing them."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS0G6(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are an expert Text-to-SQL assistant. Return only a single executable SQL query."
        base_prompt = (
            "Schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Generate one executable SQL query that answers the question.\n"
            "Return only SQL."
        )

        instructions = [
            "Return the most direct SQL query.",
            "Use only columns and tables that appear in the schema.",
            "Prefer simple standard SQL and avoid unnecessary columns.",
        ]

        sampled = []
        for instruction in instructions:
            prompt = base_prompt + "\n\n" + instruction
            try:
                response = self.llm(prompt, system=system, temperature=0.0, n=1)
            except Exception:
                response = ""

            sql = self._extract_sql(self._to_text(response))
            if sql:
                sampled.append(sql)

        if not sampled:
            try:
                response = self.llm(base_prompt, system=system, temperature=0.0, n=1)
            except Exception:
                response = ""
            return self._extract_sql(self._to_text(response))

        candidates = {}
        order = []

        for sql in sampled:
            key = self._normalize(sql)
            if key not in candidates:
                candidates[key] = {"sql": sql, "votes": 0}
                order.append(key)
            candidates[key]["votes"] += 1

        best_sql = sampled[0]
        best_score = -1

        for key in order:
            item = candidates[key]
            sql = item["sql"]
            score = item["votes"]

            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if isinstance(result, dict) and result.get("ok"):
                score += 10

            if score > best_score:
                best_score = score
                best_sql = sql

        return best_sql

    def _to_text(self, response):
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, list):
            return "\n".join(self._to_text(item) for item in response)
        if isinstance(response, dict):
            for key in ("sql", "query", "text", "content", "message"):
                if key in response:
                    return self._to_text(response[key])
            return str(response)
        return str(response)

    def _extract_sql(self, text):
        if not text:
            return ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = text

        if not sql:
            sql = text

        return self._clean_sql(sql)

    def _clean_sql(self, sql):
        sql = str(sql).strip()
        if not sql:
            return ""

        lines = []
        for line in sql.splitlines():
            line = line.strip()
            if line.startswith("