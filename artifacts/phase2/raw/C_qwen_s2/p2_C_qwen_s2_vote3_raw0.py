"""Asks the frozen solver for three independent SQL attempts, executes parseable candidates, and returns a candidate producing the majority result."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        response = self._sample_sqls(prompt)
        texts = self._completion_texts(response)[:3]

        parsed_sqls = []
        executed = []

        for text in texts:
            sql = self._extract_sql(text)
            if not sql:
                continue

            parsed_sqls.append(sql)

            try:
                result = self.execute(sql)
            except Exception:
                continue

            if isinstance(result, dict):
                ok = result.get("ok", False)
                rows = result.get("rows")
            else:
                ok = getattr(result, "ok", False)
                rows = getattr(result, "rows", None)

            if ok:
                executed.append((self._result_key(rows), sql))

        if executed:
            counts = {}
            first_sql = {}
            first_index = {}

            for idx, (key, sql) in enumerate(executed):
                counts[key] = counts.get(key, 0) + 1
                if key not in first_sql:
                    first_sql[key] = sql
                    first_index[key] = idx

            best_key = None
            best_count = -1
            best_index = len(executed)

            for key, count in counts.items():
                idx = first_index[key]
                if count > best_count or (count == best_count and idx < best_index):
                    best_key = key
                    best_count = count
                    best_index = idx

            return first_sql[best_key]

        if parsed_sqls:
            return parsed_sqls[0]

        for text in texts:
            if isinstance(text, str) and text.strip():
                return text.strip()

        return ""

    def _sample_sqls(self, prompt: str):
        try:
            return self.llm(prompt, system="", temperature=0.7, n=3)
        except TypeError:
            try:
                return self.llm(prompt, temperature=0.7, n=3)
            except TypeError:
                return self.llm(prompt)

    def _build_prompt(self, question: str) -> str:
        return (
            "Using the schema below, write a single SQL query that answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only SQL."
        )

    def _completion_texts(self, response):
        if response is None:
            return []

        if isinstance(response, str):
            return [response]

        if isinstance(response, (list, tuple)):
            texts = []
            for item in response:
                texts.extend(self._completion_texts(item))
            return texts

        if isinstance(response, dict):
            if "choices" in response:
                return self._completion_texts(response["choices"])
            for key in ("text", "completion", "content", "output", "message", "sql"):
                if key in response:
                    return self._completion_texts(response[key])
            return []

        for attr in ("choices", "text", "completion", "content", "output", "message"):
            if hasattr(response, attr):
                return self._completion_texts(getattr(response, attr))

        return [str(response)]

    def _extract_sql(self, text):
        if not isinstance(text, str):
            text = str(text)

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = None

        if not sql:
            candidate = text.strip()
            lowered = candidate.lower()
            if lowered.startswith(
                ("select", "with", "insert", "update", "delete", "pragma", "explain")
            ):
                sql = candidate

        return (sql or "").strip()

    def _result_key(self, rows):
        try:
            return repr(self._canonical_rows(rows))
        except Exception:
            try:
                return str(rows)
            except Exception:
                return "unrepresentable-result"

    def _canonical_rows(self, rows):
        if rows is None:
            return ()

        if not isinstance(rows, (list, tuple, set, frozenset)):
            try:
                rows = list(rows)
            except Exception:
                rows = [rows]

        normalized = [self._canonical_row(row) for row in rows]

        try:
            return tuple(sorted(normalized, key=repr))
        except Exception:
            try:
                return tuple(normalized)
            except Exception:
                return ()

    def _canonical_row(self, row):
        if isinstance(row, dict):
            return tuple(sorted((str(k), self._canonical_value(v)) for k, v in row.items()))

        if hasattr(row, "keys"):
            try:
                return tuple(
                    sorted((str(k), self._canonical_value(row[k])) for k in row.keys())
                )
            except Exception:
                pass

        if isinstance(row, (list, tuple)):
            return tuple(self._canonical_value(v) for v in row)

        if hasattr(row, "_asdict"):
            try:
                return tuple(
                    sorted((str(k), self._canonical_value(v)) for k, v in row._asdict().items())
                )
            except Exception:
                pass

        return self._canonical_value(row)

    def _canonical_value(self, value):
        if value is None or isinstance(value, (bool, int, float, str)):
            return value

        if isinstance(value, bytes):
            try:
                return value.decode("utf-8", "replace")
            except Exception:
                return repr(value)

        return repr(value)