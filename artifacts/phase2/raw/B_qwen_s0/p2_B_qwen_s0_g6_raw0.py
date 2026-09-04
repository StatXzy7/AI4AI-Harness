"""Draw multiple SQL samples and choose one using execution-based consensus."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS0G6(SQLHarness):
    def _response_text(self, response):
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, list):
            return "\n".join(self._response_text(item) for item in response)
        if isinstance(response, dict):
            for key in ("text", "completion", "content", "message", "output"):
                if key in response:
                    return self._response_text(response[key])
            if "choices" in response:
                return self._response_text(response["choices"])
        return str(response)

    def _extract_sql(self, text):
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""
        return sql.strip() if isinstance(sql, str) else ""

    def _result_signature(self, rows):
        try:
            row_count = len(rows)
        except Exception:
            row_count = 0

        col_count = 0
        if row_count:
            first = rows[0]
            if isinstance(first, dict):
                col_count = len(first)
            elif isinstance(first, (list, tuple, set)):
                col_count = len(first)
            else:
                col_count = 1

        return (row_count, col_count)

    def solve(self, question: str) -> str:
        system = "You are a precise Text-to-SQL engine. Return only one SQLite SQL statement."
        prompt = (
            "Write one SQLite SQL query that answers the question using the schema.\n"
            "Return only SQL, without markdown or explanation.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n"
        )

        candidates = []
        seen = set()
        raw_fallback = ""

        for temperature in (0.0, 0.3, 0.6):
            try:
                response = self.llm(prompt, system=system, temperature=temperature, n=1)
            except Exception:
                response = ""

            text = self._response_text(response)
            if not raw_fallback and text.strip():
                raw_fallback = text.strip()

            sql = self._extract_sql(text)
            if not sql:
                continue

            normalized = " ".join(sql.split()).lower().rstrip(";")
            if normalized in seen:
                continue

            seen.add(normalized)
            candidates.append(sql)

        if not candidates:
            fallback = self._extract_sql(raw_fallback)
            return fallback or "SELECT 1"

        successful = []
        for sql in candidates:
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if isinstance(result, dict) and result.get("ok"):
                rows = result.get("rows")
                successful.append((sql, rows if rows is not None else []))

        if not successful:
            return candidates[0]

        signatures = []
        signature_counts = {}

        for _, rows in successful:
            signature = self._result_signature(rows)
            signatures.append(signature)
            signature_counts[signature] = signature_counts.get(signature, 0) + 1

        best_signature = max(signature_counts.items(), key=lambda item: item[1])[0]

        for (sql, _), signature in zip(successful, signatures):
            if signature == best_signature:
                return sql

        return successful[0][0]