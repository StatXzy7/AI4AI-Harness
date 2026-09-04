"""Requests three independent SQL candidates from the frozen solver and returns the SQL whose execution result is most common."""
import json

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS0Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Using the database schema below, write a SQL query that answers the question. "
            "Return only the SQL query.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n"
        )
        system = "You are a Text-to-SQL assistant. Output only a single SQL query."

        raw = self.llm(prompt, system=system, temperature=0.7, n=3)
        texts = self._texts(raw)[:3]

        parsed_sqls = []
        successful = []

        for text in texts:
            try:
                sql = bridge.extract_sql(text)
            except Exception:
                sql = None

            if not sql:
                continue

            sql = str(sql).strip()
            if not sql:
                continue

            parsed_sqls.append(sql)

            try:
                result = self.execute(sql)
            except Exception:
                continue

            if not isinstance(result, dict) or not result.get("ok"):
                continue

            key = self._rows_key(result.get("rows", []))
            successful.append((key, sql))

        if successful:
            groups = {}
            for key, sql in successful:
                if key not in groups:
                    groups[key] = {"count": 0, "sql": sql}
                groups[key]["count"] += 1

            best_sql = None
            best_count = -1
            for info in groups.values():
                if info["count"] > best_count:
                    best_count = info["count"]
                    best_sql = info["sql"]

            if best_sql is not None:
                return best_sql

        if parsed_sqls:
            counts = {}
            order = []
            for sql in parsed_sqls:
                if sql not in counts:
                    counts[sql] = 0
                    order.append(sql)
                counts[sql] += 1

            best_sql = None
            best_count = -1
            for sql in order:
                if counts[sql] > best_count:
                    best_count = counts[sql]
                    best_sql = sql

            if best_sql is not None:
                return best_sql

        return ""

    def _texts(self, raw):
        if raw is None:
            return []

        if isinstance(raw, str):
            return [raw]

        if isinstance(raw, bytes):
            return [raw.decode("utf-8", "ignore")]

        if isinstance(raw, (list, tuple, set, frozenset)):
            out = []
            for item in raw:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, bytes):
                    out.append(item.decode("utf-8", "ignore"))
                elif isinstance(item, dict):
                    text = item.get("text")
                    if text is None and isinstance(item.get("message"), dict):
                        text = item["message"].get("content")
                    if text is None:
                        text = item.get("content")
                    out.append("" if text is None else str(text))
                elif hasattr(item, "message"):
                    message = getattr(item, "message")
                    if isinstance(message, dict):
                        text = message.get("content")
                    else:
                        text = getattr(message, "content", None)
                    out.append("" if text is None else str(text))
                elif hasattr(item, "text"):
                    out.append(str(getattr(item, "text", "") or ""))
                else:
                    out.append(str(item))
            return out

        if isinstance(raw, dict):
            choices = raw.get("choices")
            if isinstance(choices, (list, tuple, set, frozenset)):
                return self._texts(choices)
            text = raw.get("text")
            if text is None:
                text = raw.get("content")
            return ["" if text is None else str(text)]

        if hasattr(raw, "choices"):
            return self._texts(getattr(raw, "choices"))

        if hasattr(raw, "text"):
            return [str(getattr(raw, "text", "") or "")]

        return [str(raw)]

    def _rows_key(self, rows):
        if rows is None:
            rows_obj = []
        elif isinstance(rows, (list, tuple, set, frozenset)):
            rows_obj = list(rows)
        elif isinstance(rows, dict):
            rows_obj = rows
        elif isinstance(rows, (str, bytes, bytearray)):
            rows_obj = rows
        else:
            try:
                rows_obj = list(rows)
            except TypeError:
                rows_obj = rows

        try:
            return json.dumps(rows_obj, sort_keys=True, default=str)
        except Exception:
            return repr(rows_obj)