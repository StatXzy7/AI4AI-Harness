"""Draw multiple SQL samples and select the best by execution success and self-consistency."""
# MECHANISM: vote        -- you draw multiple samples and select among them

from ..harness_base import SQLHarness
from .. import bridge

class P2P2ADeepseekS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = f"Given the database schema:\n{self.schema}\n\nQuestion: {question}\n\nWrite a SQL query to answer the question."

        samples = self._draw_samples(prompt, n=5)
        if not samples:
            return ""

        extracted_sqls = []
        for text in samples:
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                extracted_sqls.append(sql.strip())

        if not extracted_sqls:
            return samples[0]

        # Normalize and count SQL strings for self-consistency voting.
        unique = {}  # normalized_sql -> dict(sql, count, ok, rows)
        for sql in extracted_sqls:
            norm = self._normalize_sql(sql)
            if norm not in unique:
                unique[norm] = {"sql": sql, "count": 0, "ok": False, "rows": 0}
            unique[norm]["count"] += 1

        # Execute each unique SQL to identify runnable candidates.
        for norm, info in unique.items():
            try:
                result = self.execute(info["sql"])
                if isinstance(result, dict) and result.get("ok"):
                    info["ok"] = True
                    rows = result.get("rows")
                    info["rows"] = len(rows) if rows is not None else 0
            except Exception:
                # Execution should not kill the harness; treat as failure.
                pass

        successful = [info for info in unique.values() if info["ok"]]
        if successful:
            # Choose most frequent successful candidate, tie-breaking by non-empty rows.
            best = max(successful, key=lambda x: (x["count"], x["rows"]))
            return best["sql"]

        # If none executed successfully, return the most common SQL still.
        best = max(unique.values(), key=lambda x: x["count"])
        return best["sql"]

    def _draw_samples(self, prompt: str, n: int = 5):
        response = self.llm(
            prompt,
            system="You are a helpful SQL expert.",
            temperature=0.7,
            n=n,
        )
        if not response:
            return []
        if isinstance(response, str):
            return [response]
        if isinstance(response, list):
            return [str(x) for x in response]
        return [str(response)]

    def _normalize_sql(self, sql: str) -> str:
        s = sql.strip()
        if s.endswith(";"):
            s = s[:-1]
        return " ".join(s.split()).lower()