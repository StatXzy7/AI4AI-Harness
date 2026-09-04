"""Ask the frozen solver for three independent SQL candidates, execute all parseable candidates, and return the SQL whose execution result forms the majority."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS1Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are an expert text-to-SQL assistant. "
            "Answer with exactly one executable SQL query and no explanation."
        )
        prompt = (
            "Given the following database schema, write a SQL query that answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL query:"
        )

        try:
            response = self.llm(prompt, system=system, temperature=0.7, n=3)
        except Exception:
            return ""

        texts = self._texts_from_response(response)

        candidates = []
        for text in texts:
            sql = self._extract_sql(text)
            if sql:
                candidates.append(sql)

        groups = {}
        for index, sql in enumerate(candidates):
            try:
                result = self.execute(sql)
            except Exception:
                continue

            if not isinstance(result, dict) or not result.get("ok", False):
                continue

            rows = result.get("rows", [])
            key = self._result_key(rows, sql)

            if key not in groups:
                groups[key] = {"count": 1, "sql": sql, "index": index}
            else:
                groups[key]["count"] += 1

        if groups:
            best = min(groups.values(), key=lambda item: (-item["count"], item["index"]))
            return best["sql"]

        if candidates:
            return candidates[0]

        return ""

    def _texts_from_response(self, response):
        if response is None:
            return []

        if isinstance(response, str):
            return [response] if response.strip() else []

        if isinstance(response, (list, tuple)):
            texts = []
            for item in response:
                if isinstance(item, (list, tuple)):
                    texts.extend(self._texts_from_response(item))
                else:
                    text = self._text_from_item(item)
                    if text and text.strip():
                        texts.append(text)
            return texts

        text = self._text_from_item(response)
        return [text] if text and text.strip() else []

    def _text_from_item(self, item):
        if item is None:
            return ""

        if isinstance(item, str):
            return item

        if isinstance(item, (list, tuple)):
            for subitem in item:
                text = self._text_from_item(subitem)
                if text:
                    return text
            return ""

        if isinstance(item, dict):
            for key in (
                "text",
                "completion",
                "content",
                "message",
                "output",
                "sql",
                "generated_text",
                "choices",
                "data",
                "results",
                "candidates",
                "generations",
            ):
                if key in item:
                    text = self._text_from_item(item[key])
                    if text:
                        return text
            return ""

        for attr in ("text", "completion", "content", "message", "output"):
            if hasattr(item, attr):
                text = self._text_from_item(getattr(item, attr))
                if text:
                    return text

        try:
            return str(item)
        except Exception:
            return ""

    def _extract_sql(self, text):
        if not text:
            return ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        if sql is None:
            return ""

        return str(sql).strip()

    def _result_key(self, rows, sql):
        normalized = self._normalize_rows(rows)

        if sql and re.search(r"\border\s+by\b", str(sql), re.IGNORECASE):
            payload = normalized
        else:
            try:
                payload = sorted(normalized, key=repr)
            except Exception:
                payload = normalized

        return repr(payload)

    def _normalize_rows(self, rows):
        if rows is None:
            return []

        if isinstance(rows, dict):
            rows = [rows]
        elif not isinstance(rows, (list, tuple)):
            try:
                rows = list(rows)
            except TypeError:
                rows = [rows]

        return [self._normalize_row(row) for row in rows]

    def _normalize_row(self, row):
        if isinstance(row, dict):
            return tuple(sorted((str(key), self._value_repr(value)) for key, value in row.items()))

        if hasattr(row, "keys") and callable(getattr(row, "keys", None)):
            try:
                return tuple(sorted((str(key), self._value_repr(row[key])) for key in row.keys()))
            except Exception:
                pass

        if isinstance(row, (list, tuple)):
            return tuple(self._value_repr(value) for value in row)

        if isinstance(row, (str, bytes)):
            return self._value_repr(row)

        try:
            return tuple(self._value_repr(value) for value in row)
        except TypeError:
            return self._value_repr(row)
        except Exception:
            return self._value_repr(row)

    def _value_repr(self, value):
        try:
            return repr(value)
        except Exception:
            try:
                return str(value)
            except Exception:
                return "<unrepresentable>"