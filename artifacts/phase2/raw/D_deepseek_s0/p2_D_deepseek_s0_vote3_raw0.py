"""Ask the solver for three independent SQL attempts at temperature 0.7, execute all parseable queries, and return the SQL whose result is the majority."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS0Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Given the following database schema:\n"
            f"{self.schema}\n\n"
            "Question: "
            f"{question}\n\n"
            "Write one SQL query that answers the question. "
            "Return only the SQL query, without any explanation or markdown fences."
        )
        system = "You are an expert SQL query generator."

        responses = self.llm(prompt, system=system, temperature=0.7, n=3)
        response_list = self._normalize_responses(responses)

        executed = []  # list of (sql, result_key)
        for response in response_list:
            sql = bridge.extract_sql(response)
            if not sql:
                continue
            try:
                result = self.execute(sql)
            except Exception:
                continue
            if result.get("ok"):
                rows = result.get("rows", [])
                executed.append((sql, self._rows_key(rows)))

        if not executed:
            # Fallback: first parseable SQL if no query executed successfully
            for response in response_list:
                sql = bridge.extract_sql(response)
                if sql:
                    return sql
            return ""

        counts = {}
        for _, key in executed:
            counts[key] = counts.get(key, 0) + 1

        best_key = max(counts, key=lambda k: counts[k])

        for sql, key in executed:
            if key == best_key:
                return sql

        return executed[0][0]

    @staticmethod
    def _normalize_responses(responses):
        if isinstance(responses, str):
            return [responses]

        if hasattr(responses, "choices"):
            responses = responses.choices

        if isinstance(responses, (list, tuple)):
            out = []
            for r in responses:
                if isinstance(r, str):
                    out.append(r)
                elif hasattr(r, "text"):
                    out.append(r.text)
                elif hasattr(r, "message"):
                    out.append(r.message.content)
                elif isinstance(r, dict):
                    out.append(r.get("text") or r.get("content") or str(r))
                else:
                    out.append(str(r))
            return out

        return [str(responses)]

    def _rows_key(self, rows):
        if rows is None:
            return (None,)
        if not isinstance(rows, list):
            rows = list(rows)
        return tuple(self._normalize_row(row) for row in rows)

    def _normalize_row(self, row):
        if isinstance(row, dict):
            return tuple((key, self._normalize_value(value)) for key, value in sorted(row.items()))
        if isinstance(row, (list, tuple)):
            return tuple(self._normalize_value(value) for value in row)
        return self._normalize_value(row)

    def _normalize_value(self, value):
        if isinstance(value, dict):
            return tuple((key, self._normalize_value(val)) for key, val in sorted(value.items()))
        if isinstance(value, (list, tuple)):
            return tuple(self._normalize_value(val) for val in value)
        return repr(value)