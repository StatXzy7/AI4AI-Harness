"""Ask the frozen solver for three independent SQL attempts and return the majority executable result."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS0Vote3(SQLHarness):
    """Ask the frozen solver for three independent SQL attempts and return the majority executable result."""

    def solve(self, question: str) -> str:
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. "
            "Return only the SQL query, without explanation or markdown."
        )

        try:
            raw = self.llm(prompt, temperature=0.7, n=3)
        except Exception:
            return ""

        parsed_sql = []
        for text in self._to_texts(raw):
            try:
                sql = bridge.extract_sql(text)
            except Exception:
                sql = None

            if sql is None:
                continue

            sql = str(sql).strip()
            if sql:
                parsed_sql.append(sql)

        candidates = []
        for sql in parsed_sql:
            try:
                result = self.execute(sql)
            except Exception:
                continue

            if isinstance(result, dict) and result.get("ok"):
                candidates.append((sql, result.get("rows", [])))

        if candidates:
            chosen = self._choose_majority(candidates)
            if chosen:
                return chosen

        if parsed_sql:
            return parsed_sql[0]

        return ""

    def _choose_majority(self, candidates):
        for key_fn in (self._exact_result_key, self._unordered_result_key):
            counts = {}
            for _, rows in candidates:
                key = key_fn(rows)
                counts[key] = counts.get(key, 0) + 1

            best_count = max(counts.values()) if counts else 0
            if best_count >= 2:
                for sql, rows in candidates:
                    if counts.get(key_fn(rows), 0) == best_count:
                        return sql

        return candidates[0][0] if candidates else None

    def _exact_result_key(self, rows):
        try:
            return repr(self._canonical_rows(rows))
        except Exception:
            try:
                return str(rows)
            except Exception:
                return "<unrepresentable-result>"

    def _unordered_result_key(self, rows):
        try:
            canonical = self._canonical_rows(rows)
            row_reprs = [repr(row) for row in canonical]
            return repr(sorted(row_reprs))
        except Exception:
            return self._exact_result_key(rows)

    def _canonical_rows(self, rows):
        try:
            if isinstance(rows, (list, tuple)):
                return tuple(self._canonical_row(row) for row in rows)
            if isinstance(rows, dict):
                return (self._canonical_row(rows),)
            return (repr(rows),)
        except Exception:
            try:
                return (str(rows),)
            except Exception:
                return ("<unrepresentable-rows>",)

    def _canonical_row(self, row):
        try:
            if isinstance(row, (str, bytes, bytearray)):
                return (repr(row),)

            if isinstance(row, dict):
                return tuple(
                    (str(k), repr(v))
                    for k, v in sorted(row.items(), key=lambda item: str(item[0]))
                )

            if isinstance(row, (list, tuple)):
                return tuple(repr(v) for v in row)

            keys = getattr(row, "keys", None)
            if callable(keys):
                try:
                    return tuple((str(k), repr(row[k])) for k in keys())
                except Exception:
                    pass

            try:
                return tuple(repr(v) for v in row)
            except Exception:
                return (repr(row),)
        except Exception:
            try:
                return (repr(row),)
            except Exception:
                try:
                    return (str(row),)
                except Exception:
                    return ("<unrepresentable-row>",)

    def _to_texts(self, raw):
        try:
            if raw is None:
                return []

            if isinstance(raw, str):
                return [raw]

            if isinstance(raw, dict):
                if "choices" in raw and raw["choices"] is not None:
                    texts = self._to_texts(raw["choices"])
                    if texts:
                        return texts

                if "message" in raw and raw["message"] is not None:
                    texts = self._to_texts(raw["message"])
                    if texts:
                        return texts

                for key in ("text", "content", "completion", "output", "result"):
                    if key in raw and raw[key] is not None:
                        texts = self._to_texts(raw[key])
                        if texts:
                            return texts

                return [str(raw)]

            if isinstance(raw, (list, tuple)):
                texts = []
                for item in raw:
                    texts.extend(self._to_texts(item))
                return texts

            choices = getattr(raw, "choices", None)
            if choices is not None:
                texts = self._to_texts(choices)
                if texts:
                    return texts

            message = getattr(raw, "message", None)
            if message is not None:
                texts = self._to_texts(message)
                if texts:
                    return texts

            text = getattr(raw, "text", None)
            if text is not None:
                texts = self._to_texts(text)
                if texts:
                    return texts

            content = getattr(raw, "content", None)
            if content is not None:
                texts = self._to_texts(content)
                if texts:
                    return texts

            return [str(raw)]
        except Exception:
            try:
                return [str(raw)]
            except Exception:
                return []