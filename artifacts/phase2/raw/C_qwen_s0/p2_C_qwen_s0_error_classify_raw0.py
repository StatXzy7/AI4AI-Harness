"""Generates SQL, executes it, classifies failures as syntax/schema/semantics, and applies targeted repairs for up to two rounds."""
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2CQwenS0ErrorClassify(SQLHarness):
    MAX_REPAIR_ROUNDS = 2

    def solve(self, question: str) -> str:
        question = str(question or "").strip()
        schema = str(getattr(self, "schema", "") or "")

        sql = self._initial_sql(question, schema)
        best_sql = ""
        previous_sql = ""
        seen = set()

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            if not sql:
                sql = previous_sql or best_sql
            if not sql:
                break

            sql_key = self._normalize_sql(sql)
            if sql_key in seen:
                break
            seen.add(sql_key)

            result = self._execute(sql)

            if result.get("ok"):
                best_sql = sql
                if round_idx >= self.MAX_REPAIR_ROUNDS:
                    return sql

                issue = self._semantic_issue_on_success(question, sql, result)
                if not issue:
                    return sql

                failure_class = "semantics"
                details = issue
            else:
                if round_idx >= self.MAX_REPAIR_ROUNDS:
                    break

                failure_class = self._classify_error(result.get("error", ""), sql)
                details = result.get("error", "") or "execution failed"

            previous_sql = sql

            if failure_class == "syntax":
                fixed = self._fix_syntax(question, schema, sql, details)
            elif failure_class == "schema":
                fixed = self._fix_schema(question, schema, sql, details)
            else:
                fixed = self._fix_semantics(question, schema, sql, result, details)

            if not fixed or self._normalize_sql(fixed) == sql_key:
                break

            sql = fixed

        if best_sql:
            return best_sql
        return sql or previous_sql or ""

    def _llm_text(self, prompt, system="", temperature=0.0):
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            return ""
        return self._to_text(response).strip()

    def _to_text(self, value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            return "\n".join(self._to_text(item) for item in value)
        if isinstance(value, dict):
            for key in ("text", "completion", "content", "answer", "sql", "message", "output"):
                if key in value:
                    return self._to_text(value[key])
            return str(value)

        for attr in ("choices", "message", "text"):
            if hasattr(value, attr):
                try:
                    return self._to_text(getattr(value, attr))
                except Exception:
                    pass

        return str(value)

    def _extract_sql(self, text):
        text = self._to_text(text).strip()
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
            extracted = self._to_text(extracted).strip()
            if extracted:
                return extracted.rstrip(";").strip()
        except Exception:
            pass

        cleaned = text.strip()
        fence = re.search(r"