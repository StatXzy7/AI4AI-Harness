"""Format-guarded Text-to-SQL harness that forces a single fenced SQL answer and retries format or schema violations."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS0FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        schema = str(getattr(self, "schema", "") or "")
        question = str(question or "")
        system = self._system_prompt()

        best_sql = ""
        raw = ""
        issue = None
        execution_error = ""
        seen_sqls = set()
        max_attempts = 5

        for attempt in range(max_attempts):
            if attempt == 0 or issue is None:
                prompt = self._initial_prompt(question, schema)
            elif issue == "format":
                prompt = self._format_repair_prompt(raw, question, schema)
            elif issue == "sql":
                prompt = self._sql_repair_prompt(best_sql, question, schema)
            elif issue == "execution":
                prompt = self._execution_repair_prompt(best_sql, execution_error, question, schema)
            else:
                prompt = self._initial_prompt(question, schema)

            raw = self._call_llm(prompt, system)
            sql = self._extract_sql(raw)

            if sql:
                best_sql = sql

            if not self._has_only_sql_fence(raw):
                issue = "format"
                continue

            if not sql or not self._basic_sql_ok(sql):
                issue = "sql"
                continue

            normalized_sql = sql.strip().rstrip(";").strip()
            if normalized_sql in seen_sqls:
                return self._finalize_sql(normalized_sql)
            seen_sqls.add(normalized_sql)

            result = self._safe_execute(sql)
            if result is None:
                return self._finalize_sql(sql)

            if result.get("ok"):
                return self._finalize_sql(sql)

            execution_error = str(result.get("error") or "SQL execution failed")
            issue = "execution"

        if best_sql:
            return self._finalize_sql(best_sql)

        fallback = self._strip_sql_fence(raw)
        if self._looks_like_sql(fallback):
            return self._finalize_sql(fallback)

        return ""

    def _system_prompt(self) -> str:
        return (
            "You are a strict Text-to-SQL assistant. "
            "Your entire reply must be exactly one SQL query inside a