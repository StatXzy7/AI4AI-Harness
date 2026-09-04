"""Improves Text-to-SQL by sampling multiple candidate queries and voting on their execution results."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS1G7(SQLHarness):
    """Generate multiple SQL candidates and select by execution-result agreement."""

    SAMPLES = 3
    DIVERSITY_TEMPERATURE = 0.7

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL system. Produce a single valid SQL query "
            "that answers the question using only the provided schema."
        )
        prompt = self._generation_prompt(question)

        candidates = []
        raw_texts = []

        for idx in range(self.SAMPLES):
            temperature = 0.0 if idx == 0 else self.DIVERSITY_TEMPERATURE
            try:
                response = self.llm(prompt, system=system, temperature=temperature, n=1)
            except Exception:
                response = ""

            text = self._response_to_text(response)
            raw_texts.append(text)

            sql = self._extract_sql(text)
            if sql:
                candidates.append(sql)

        if not candidates:
            fallback = self._extract_sql("\n".join(raw_texts))
            if fallback:
                return fallback
            return raw_texts[0].strip() if raw_texts else ""

        scored = []
        for idx, sql in enumerate(candidates):
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": None, "error": str(exc)}

            ok = bool(result.get("ok")) if isinstance(result, dict) else False
            rows = result.get("rows") if isinstance(result, dict) else None
            error = result.get("error") if isinstance(result, dict) else "Execution failed"

            scored.append(
                {
                    "idx": idx,
                    "sql": sql,
                    "ok": ok,
                    "key": self._result_key(ok, rows, error),
                    "length": len(sql),
                }
            )

        groups = {}
        for item in scored:
            groups.setdefault(item["key"], []).append(item)

        ok_groups = [items for items in groups.values() if items and items[0]["ok"]]
        if ok_groups:
            ok_groups.sort(
                key=lambda items: (
                    -len(items),
                    min(item["idx"] for item in items),
                    min(item["length"] for item in items),
                )
            )
            return ok_groups[0][0]["sql"]

        sql_groups = {}
        for item in scored:
            sql_groups.setdefault(self._normalize_sql(item["sql"]), []).append(item)

        fallback_groups = sorted(
            sql_groups.values(),
            key=lambda items: (
                -len(items),
                min(item["idx"] for item in items),
                min(item["length"] for item in items),
            ),
        )
        return fallback_groups[0][0]["sql"]

    def _generation_prompt(self, question: str) -> str:
        return (
            "Given the database schema below, write one SQL query that answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only the SQL query, without explanation."
        )

    def _response_to_text(self, response) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, list):
            if not response:
                return ""
            return self._response_to_text(response[0])
        if isinstance(response, dict):
            for key in ("text", "completion", "content", "output"):
                if key in response:
                    return self._response_to_text(response[key])
            choices = response.get("choices")
            if choices:
                return self._response_to_text(choices[0])
            if "message" in response:
                return self._response_to_text(response["message"])
        return str(response)

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        if extracted is None:
            extracted = ""

        extracted = str(extracted).strip()
        if extracted:
            return extracted

        cleaned = text.strip().strip("`").strip()
        if cleaned.upper().startswith(
            ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER")
        ):
            return cleaned

        return ""

    def _result_key(self, ok: bool, rows, error) -> str:
        if not ok:
            return "error:" + self._short(str(error or ""))
        return "ok:" + self._stable_rows(rows)

    def _stable_rows(self, rows) -> str:
        if rows is None:
            return "none"

        try:
            if isinstance(rows, (list, tuple)):
                normalized = []
                for row in rows:
                    if isinstance(row, dict):
                        normalized.append(
                            repr(sorted((str(k), repr(v)) for k, v in row.items()))
                        )
                    elif isinstance(row, (list, tuple)):
                        normalized.append(repr([repr(value) for value in row]))
                    else:
                        normalized.append(repr(row))
                return "rows=" + ";".join(sorted(normalized))

            return "value=" + repr(rows)
        except Exception:
            return "raw=" + self._short(repr(rows))

    def _normalize_sql(self, sql: str) -> str:
        return " ".join(str(sql).strip().lower().split())

    def _short(self, text: str, limit: int = 300) -> str:
        text = str(text)
        return text if len(text) <= limit else text[:limit] + "..."