"""Samples multiple candidate SQL queries and selects the best using execution-based voting."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS1G6(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        system = (
            "You are an expert Text-to-SQL assistant. "
            "Return only one executable SQL query. No explanations."
        )

        base_prompt = (
            "Write a SQL query that answers the question using the schema.\n"
            "Return only SQL.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n"
        )

        prompts = [
            base_prompt + "\nPrefer the most direct, minimal SQL.",
            base_prompt + "\nDouble-check table names, column names, and join conditions.",
            base_prompt + "\nIf grouping or aggregation is needed, make the GROUP BY clause complete.",
        ]

        samples = []
        for prompt in prompts:
            try:
                raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            except Exception:
                raw = ""
            sql = self._extract_sql(raw)
            if sql:
                samples.append(sql)

        if not samples:
            try:
                raw = self.llm(base_prompt, system=system, temperature=0.0, n=1)
            except Exception:
                raw = ""
            sql = self._extract_sql(raw)
            return sql or raw.strip() or "SELECT 1"

        vote_counts = {}
        representative = {}
        order = []

        for sql in samples:
            norm = self._normalize_sql(sql)
            if norm not in vote_counts:
                vote_counts[norm] = 0
                representative[norm] = sql
                order.append(norm)
            vote_counts[norm] += 1

        ok_records = []
        for idx, norm in enumerate(order):
            sql = representative[norm]
            result = self._safe_execute(sql)
            if result.get("ok"):
                ok_records.append(
                    {
                        "idx": idx,
                        "sql": sql,
                        "votes": vote_counts[norm],
                        "rows": result.get("rows", []),
                        "signature": self._result_signature(result),
                    }
                )

        if not ok_records:
            return samples[0]

        signature_scores = {}
        for rec in ok_records:
            signature_scores[rec["signature"]] = (
                signature_scores.get(rec["signature"], 0) + rec["votes"]
            )

        best = None
        best_key = None

        for rec in ok_records:
            nonempty = 1 if rec["rows"] else 0
            key = (
                signature_scores[rec["signature"]],
                rec["votes"],
                nonempty,
                -len(rec["sql"]),
                -rec["idx"],
            )
            if best_key is None or key > best_key:
                best_key = key
                best = rec

        return best["sql"] if best else samples[0]

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = None

        if not sql:
            sql = text

        if not isinstance(sql, str):
            sql = str(sql)

        sql = sql.strip()
        if sql.endswith(";"):
            sql = sql[:-1].strip()

        return sql

    def _normalize_sql(self, sql: str) -> str:
        return " ".join((sql or "").split())

    def _safe_execute(self, sql: str):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if not isinstance(result, dict):
            return {"ok": bool(result), "rows": [], "error": ""}

        return result

    def _result_signature(self, result) -> str:
        try:
            rows = result.get("rows", [])
            if isinstance(rows, list):
                preview = rows[:20]
                return repr((len(rows), preview))[:2000]
            return repr(rows)[:2000]
        except Exception:
            try:
                return f"rows:{len(result.get('rows', []))}"
            except Exception:
                return ""