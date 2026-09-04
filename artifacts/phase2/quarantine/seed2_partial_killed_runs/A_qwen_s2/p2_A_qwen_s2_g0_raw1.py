"""Generate multiple SQL candidates and select the most common executable candidate."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        hints = [
            "Prefer the simplest correct SQL that directly answers the question.",
            "Be careful to use exact table and column names from the schema.",
            "If grouping or aggregation is needed, group by every non-aggregated column.",
        ]

        candidates = []
        for i, hint in enumerate(hints):
            prompt = self._build_prompt(question, hint)
            temperature = 0.0 if i == 0 else 0.7
            raw = self.llm(
                prompt,
                system=self._system_prompt(),
                temperature=temperature,
                n=1,
            )
            text = self._as_text(raw)
            sql = self._extract_sql(text)
            if sql:
                candidates.append(sql)

        if not candidates:
            return ""

        executable = []
        for sql in candidates:
            result = self._safe_execute(sql)
            if result.get("ok"):
                executable.append(sql)

        pool = executable if executable else candidates
        return self._vote(pool)

    def _system_prompt(self) -> str:
        return "You are an expert Text-to-SQL engineer. Output only one executable SQL statement."

    def _build_prompt(self, question: str, hint: str) -> str:
        schema = getattr(self, "schema", "") or ""
        return (
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            f"Guidance: {hint}\n\n"
            "Return only SQL. No explanation, no markdown."
        )

    def _as_text(self, raw) -> str:
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list):
            return self._as_text(raw[0]) if raw else ""
        if isinstance(raw, dict):
            for key in ("text", "completion", "content", "output"):
                if key in raw:
                    return self._as_text(raw[key])
        return str(raw)

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
            if extracted and extracted.strip():
                return extracted.strip()
        except Exception:
            pass

        sql = text.strip()
        if "