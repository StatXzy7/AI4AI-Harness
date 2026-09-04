"""Samples multiple SQL candidates and votes on the most consistent executable result."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS1G6(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        system = (
            "You are an expert SQL engineer. Write one SQL query that answers the user's question. "
            "Return only the SQL statement, without explanation."
        )
        base_prompt = (
            "Given the following database schema, answer the question with one SQL query.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL query only:"
        )

        prompts = [
            base_prompt,
            base_prompt + "\n\nWrite the most direct SQL query. Return only SQL.",
            base_prompt + "\n\nCarefully choose the correct tables and columns. Return only SQL.",
        ]

        candidates = []
        seen_norms = set()
        raw_fallback = ""

        for idx, prompt in enumerate(prompts):
            try:
                response = self.llm(prompt, system=system, temperature=0.7, n=1)
            except Exception:
                response = ""

            text = self._text_from_llm(response)
            if text and not raw_fallback:
                raw_fallback = text.strip()

            sql = self._extract_sql(text)
            if not sql or not self._is_select_like(sql):
                continue

            norm = self._normalize_sql(sql)
            if not norm:
                continue

            if norm in seen_norms:
                for candidate in candidates:
                    if candidate["norm"] == norm:
                        candidate["votes"] += 1
                        break
                continue

            seen_norms.add(norm)
            candidates.append(
                {
                    "sql": sql,
                    "norm": norm,
                    "votes": 1,
                    "index": idx,
                }
            )

        successful = []
        for candidate in candidates:
            result = self._safe_execute(candidate["sql"])
            if result.get("ok"):
                rows = result.get("rows", [])
                candidate["row_count"] = len(rows)
                candidate["col_count"] = self._column_count(rows)
                candidate["fingerprint"] = self._result_fingerprint(rows)
                successful.append(candidate)

        if successful:
            groups = {}
            order = []

            for candidate in successful:
                fingerprint = candidate["fingerprint"]
                if fingerprint not in groups:
                    groups[fingerprint] = {
                        "votes": 0,
                        "candidates": [],
                    }
                    order.append(fingerprint)

                groups[fingerprint]["votes"] += candidate["votes"]
                groups[fingerprint]["candidates"].append(candidate)

            best_fingerprint = None
            best_votes = -1

            for fingerprint in order:
                votes = groups[fingerprint]["votes"]
                if votes > best_votes:
                    best_votes = votes
                    best_fingerprint = fingerprint

            if best_fingerprint is not None:
                return groups[best_fingerprint]["candidates"][0]["sql"]

        if candidates:
            return candidates[0]["sql"]

        if raw_fallback:
            extracted = self._extract_sql(raw_fallback)
            if extracted and self._is_select_like(extracted):
                return extracted
            if "select" in raw_fallback.lower():
                return raw_fallback

        return "SELECT 1"

    def _text_from_llm(self, response):
        if response is None:
            return ""

        if isinstance(response, str):
            return response

        if isinstance(response, (bytes, bytearray)):
            return response.decode("utf-8", "ignore")

        if isinstance(response, (list, tuple)):
            return self._text_from_llm(response[0]) if response else ""

        if isinstance(response, dict):
            for key in (
                "text",
                "completion",
                "content",
                "output",
                "message",
                "generated_text",
                "sql",
            ):
                if key in response:
                    return self._text_from_llm(response[key])

            if "choices" in response:
                return self._text_from_llm(response["choices"])

            return ""

        text_attr = getattr(response, "text", None)
        if isinstance(text_attr, str):
            return text_attr

        choices = getattr(response, "choices", None)
        if choices is not None:
            return self._text_from_llm(choices)

        content = getattr(response, "content", None)
        if content is not None:
            return self._text_from_llm(content)

        message = getattr(response, "message", None)
        if message is not None:
            return self._text_from_llm(message)

        return str(response)

    def _extract_sql(self, text):
        if not text:
            return ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        if not sql:
            return ""

        sql = str(sql).strip()
        while sql.endswith(";"):
            sql = sql[:-1].strip()

        return sql

    def _is_select_like(self, sql):
        head = sql.strip().lower()
        return head.startswith("select") or head.startswith("with")

    def _normalize_sql(self, sql):
        return " ".join(sql.lower().split())

    def _safe_execute(self, sql):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "Unexpected execution result"}

        return result

    def _column_count(self, rows):
        if not rows:
            return 0

        first = rows[0]
        if isinstance(first, dict):
            return len(first)

        try:
            return len(first)
        except TypeError:
            return 1

    def _result_fingerprint(self, rows):
        try:
            return tuple(sorted(repr(row) for row in rows))
        except Exception:
            return (repr(rows),)