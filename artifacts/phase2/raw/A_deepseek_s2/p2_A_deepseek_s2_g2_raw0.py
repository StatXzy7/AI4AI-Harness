"""Generate multiple SQL candidates and vote by executing them against the database."""
# MECHANISM: vote        -- you draw multiple samples and select among them

from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G2(SQLHarness):

    def solve(self, question: str) -> str:
        candidates = self._generate_candidates(question)
        scored = []
        for raw in candidates:
            sql = bridge.extract_sql(raw)
            if not sql:
                continue
            score, nrows, sql = self._score_sql(sql)
            scored.append((score, nrows, -len(sql), sql))

        if not scored:
            # Fallback to a single greedy call if no candidate produced SQL.
            raw = self.llm(
                self._prompt(question),
                system="You are a SQL expert. Output only SQL.",
                temperature=0.0,
                n=1,
            )
            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            return bridge.extract_sql(raw)

        # Sort by execution score, then number of returned rows, then shorter SQL.
        scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return scored[0][3]

    def _generate_candidates(self, question: str):
        raw = self.llm(
            self._prompt(question),
            system="You are a SQL expert. Output only SQL.",
            temperature=0.4,
            n=5,
        )
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            return [raw]

        # Tolerate common API wrappers that return dictionaries.
        if isinstance(raw, dict):
            if "choices" in raw:
                out = []
                for choice in raw["choices"]:
                    if isinstance(choice, dict):
                        out.append(
                            choice.get("text")
                            or choice.get("message", {}).get("content")
                            or ""
                        )
                    else:
                        out.append(str(choice))
                return out
            if "text" in raw:
                return [raw["text"]]

        return [str(raw)]

    def _score_sql(self, sql: str):
        try:
            result = self.execute(sql)
        except Exception:
            return (-1000.0, 0, sql)

        if not isinstance(result, dict):
            return (-900.0, 0, sql)

        ok = bool(result.get("ok", False))
        rows = result.get("rows", []) if ok else []
        if rows is None:
            rows = []

        if not ok:
            return (-100.0, 0, sql)

        nrows = len(rows)
        score = 1000.0
        if nrows > 0:
            score += 100.0 + min(nrows, 20)
        return (score, nrows, sql)

    def _prompt(self, question: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query to answer the question. Output only SQL."
        )