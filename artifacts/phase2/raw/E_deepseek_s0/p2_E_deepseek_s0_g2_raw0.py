"""Execution-guided multi-candidate SQL generation with error-based repair for Text-to-SQL."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G2(SQLHarness):
    @staticmethod
    def _response_to_str(response):
        if isinstance(response, list):
            return response[0] if response else ""
        return response or ""

    def solve(self, question: str) -> str:
        schema = self.schema
        system = "You are an expert SQLite query writer."

        def build_prompt(error_block=None):
            if error_block:
                return (
                    f"### Database schema\n{schema}\n\n"
                    f"### Question\n{question}\n\n"
                    "Previous attempts failed:\n"
                    f"{error_block}\n\n"
                    "Write a corrected SQLite SELECT query that answers the question.\n"
                    "Output only the raw SQL query, no explanation."
                )
            return (
                f"### Database schema\n{schema}\n\n"
                f"### Question\n{question}\n\n"
                "Write a SQLite SELECT query that answers the question.\n"
                "Output only the raw SQL query, no explanation."
            )

        candidates = []
        ok_without_rows = None

        # Phase 1: diverse candidate generation and execution
        for _ in range(3):
            raw = self._response_to_str(
                self.llm(build_prompt(), system=system, temperature=0.2, n=1)
            )
            sql = bridge.extract_sql(raw)
            if not sql:
                continue
            result = self.execute(sql)
            candidates.append((sql, result))
            if result.get("ok"):
                if result.get("rows"):
                    return sql
                if ok_without_rows is None:
                    ok_without_rows = sql

        # If one query was valid but returned no rows, return it rather than repairing.
        if ok_without_rows is not None:
            return ok_without_rows

        # Phase 2: error-aware repair
        error_block = "\n\n".join(
            f"SQL: {sql}\nError: {res.get('error')}"
            for sql, res in candidates
            if res and not res.get("ok")
        )
        if not error_block:
            # No failed SQL generated; fall back to first candidate or empty.
            return candidates[0][0] if candidates else ""

        raw = self._response_to_str(
            self.llm(build_prompt(error_block), system=system, temperature=0.0, n=1)
        )
        sql = bridge.extract_sql(raw)
        if not sql:
            return candidates[0][0] if candidates else ""

        result = self.execute(sql)
        if result.get("ok"):
            return sql

        # Return repaired SQL even if execution failed, to provide a best-effort answer.
        return sql