"""Sample three SQL candidates at temperature 0.7, execute all parseable ones, and return the SQL whose execution result occurs most often."""

import json
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Generate one SQL query that answers the question using the provided schema.\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query, without explanation or markdown."
        )
        system = "You are an expert text-to-SQL system. Output exactly one SQL query."

        try:
            response = self.llm(prompt, system=system, temperature=0.7, n=3)
        except Exception:
            response = []

        candidate_texts = self._candidate_texts(response)
        parsed_sqls = []
        executed = []

        for idx, text in enumerate(candidate_texts):
            sql = self._extract_sql(text)
            if not sql:
                continue

            parsed_sqls.append(sql)
            result = self._execute_sql(sql)

            if result.get("ok"):
                executed.append((idx, sql, self._result_key(result.get("rows"))))

        if executed:
            counts = {}
            first_index = {}
            first_sql = {}

            for idx, sql, key in executed:
                counts[key] = counts.get(key, 0) + 1
                if key not in first_index:
                    first_index[key] = idx
                    first_sql[key] = sql

            best_key = max(counts, key=lambda k: (counts[k], -first_index[k]))
            return first_sql[best_key]

        if parsed_sqls:
            return self._majority_parsed_sql(parsed_sqls)

        return "SELECT 1"

    def _candidate_texts(self, response):
        if response is None:
            return []

        if isinstance(response, str):
            return [response]

        if isinstance(response, bytes):
            return [response.decode("utf-8", errors="ignore")]

        if isinstance(response, dict):
            choices = response.get("choices")
            if isinstance(choices, (list, tuple)):
                return self._candidate_texts(choices)

            for key in ("text", "completion", "content", "message", "output"):
                value = response.get(key)
                if isinstance(value, str):
                    return [value]
                if isinstance(value, (list, tuple)):
                    return self._candidate_texts(value)
                if isinstance(value, dict):
                    content = value.get("content")
                    if isinstance(content, str):
                        return [content]

            return [str(response)]

        if isinstance(response, (list, tuple)):
            texts = []
            for item in response:
                texts.extend(self._candidate_texts(item))
            return texts

        for attr in ("text", "completion", "content", "message"):
            if hasattr(response, attr):
                try:
                    return self._candidate_texts(getattr(response, attr))
                except Exception:
                    pass

        return [str(response)]

    def _extract_sql(self, text):
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        if sql is None:
            sql = ""
        if not isinstance(sql, str):
            sql = str(sql)

        return sql.strip()

    def _execute_sql(self, sql):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return result

        return {"ok": False, "rows": result, "error": "unexpected execute result"}

    def _result_key(self, rows):
        if rows is None:
            return ()

        if not isinstance(rows, (list, tuple)):
            rows = [rows]

        serialized_rows = []

        for row in rows:
            normalized_row = row

            try:
                if hasattr(normalized_row, "keys"):
                    normalized_row = {key: normalized_row[key] for key in normalized_row.keys()}
            except Exception:
                pass

            try:
                serialized_rows.append(json.dumps(normalized_row, sort_keys=True, default=str))
            except Exception:
                try:
                    serialized_rows.append(repr(normalized_row))
                except Exception:
                    serialized_rows.append("<unserializable row>")

        return tuple(sorted(serialized_rows))

    def _majority_parsed_sql(self, parsed_sqls):
        counts = Counter()
        first_index = {}
        original_sql = {}

        for idx, sql in enumerate(parsed_sqls):
            norm = self._normalize_sql(sql)
            counts[norm] += 1

            if norm not in first_index:
                first_index[norm] = idx
                original_sql[norm] = sql

        best_norm = max(counts, key=lambda norm: (counts[norm], -first_index[norm]))
        return original_sql[best_norm]

    def _normalize_sql(self, sql):
        return " ".join(sql.strip().split()).lower()