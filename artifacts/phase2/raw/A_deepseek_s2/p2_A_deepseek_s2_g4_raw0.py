"""Generate multiple SQL candidates and return the most common normalized query."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge

class P2P2ADeepseekS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are a text-to-SQL assistant."
        prompt = f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nWrite a SQL query:"

        candidates = []
        for _ in range(5):
            raw = self.llm(prompt, system=system, temperature=0.2, n=1)
            sql = self._extract_sql(raw)
            if sql:
                candidates.append(sql)

        if not candidates:
            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            return self._extract_sql(raw) or ""

        groups = {}
        for sql in candidates:
            norm = self._normalize(sql)
            groups.setdefault(norm, []).append(sql)

        best_norm = max(groups.keys(), key=lambda k: (len(groups[k]), -len(k)))
        return groups[best_norm][0]

    def _extract_sql(self, raw) -> str:
        if isinstance(raw, str):
            return bridge.extract_sql(raw) or ""
        if isinstance(raw, (list, tuple)):
            for item in raw:
                text = item if isinstance(item, str) else str(item)
                sql = bridge.extract_sql(text)
                if sql:
                    return sql
            return ""
        if raw is not None:
            return bridge.extract_sql(str(raw)) or ""
        return ""

    @staticmethod
    def _normalize(sql: str) -> str:
        return " ".join(sql.strip().rstrip(";").strip().split())