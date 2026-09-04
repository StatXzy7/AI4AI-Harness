"""Ask the frozen solver for three sampled SQL queries, execute all parseable candidates, and return the query whose execution result occurs most often."""

from collections import Counter
import json

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS1Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are an expert SQL assistant. Output only a single SQL query."
        prompt = (
            "Write a SQL query that answers the question using the given schema.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )

        try:
            response = self.llm(prompt, system=system, temperature=0.7, n=3)
        except Exception:
            response = []

        texts = self._texts(response)[:3]
        candidates = []

        for text in texts:
            try:
                sql = bridge.extract_sql(text)
            except Exception:
                sql = ""

            if sql is None:
                continue

            sql = str(sql).strip()
            if sql:
                candidates.append(sql)

        executions = []

        for sql in candidates:
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if isinstance(result, dict) and result.get("ok"):
                rows = result.get("rows", [])
                executions.append(
                    {
                        "sql": sql,
                        "exact": self._exact_key(rows),
                        "unordered": self._unordered_key(rows),
                    }
                )

        if executions:
            exact_counts = Counter(item["exact"] for item in executions)
            best_exact = max(exact_counts.values())

            if best_exact >= 2 or len(executions) == 1:
                for item in executions:
                    if exact_counts[item["exact"]] == best_exact:
                        return item["sql"]

            unordered_counts = Counter(item["unordered"] for item in executions)
            best_unordered = max(unordered_counts.values())

            if best_unordered >= 2 or len(executions) == 1:
                for item in executions:
                    if unordered_counts[item["unordered"]] == best_unordered:
                        return item["sql"]

            return executions[0]["sql"]

        if candidates:
            return candidates[0]

        return ""

    def _texts(self, response):
        if response is None:
            return []

        if isinstance(response, str):
            return [response]

        if isinstance(response, (list, tuple, set)):
            out = []
            for item in response:
                out.extend(self._texts(item))
            return out

        if isinstance(response, dict):
            for key in ("text", "completion", "content", "output", "message", "choices"):
                if key in response:
                    return self._texts(response[key])
            return [str(response)]

        for attr in ("text", "completion", "content", "output", "message", "choices"):
            if hasattr(response, attr):
                value = getattr(response, attr)
                if value is not response and not callable(value):
                    return self._texts(value)

        return [str(response)]

    def _rows_list(self, rows):
        if rows is None:
            return []

        if isinstance(rows, (list, tuple)):
            return list(rows)

        if isinstance(rows, (str, bytes, dict)):
            return [rows]

        try:
            return list(rows)
        except Exception:
            return [rows]

    def _safe_json(self, obj):
        try:
            return json.dumps(obj, sort_keys=True, default=str)
        except Exception:
            try:
                return repr(obj)
            except Exception:
                return str(obj)

    def _exact_key(self, rows):
        return self._safe_json(self._rows_list(rows))

    def _unordered_key(self, rows):
        parts = [self._safe_json(row) for row in self._rows_list(rows)]
        parts.sort()
        return self._safe_json(parts)