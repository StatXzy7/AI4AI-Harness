"""Majority-vote harness that asks the solver for three SQL attempts at temperature 0.7, executes all parsed queries, and returns the SQL whose result set is most common."""
import json

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS1Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query that answers the question. Return only the SQL, without markdown or explanation."
        )
        system = "You are an expert SQL query generator. Answer with only SQL."

        raw_responses = self.llm(prompt, system=system, temperature=0.7, n=3)

        if isinstance(raw_responses, list):
            responses = raw_responses
        else:
            responses = [raw_responses]

        parsed_sqls = []
        successful_sqls = []
        result_groups = {}

        for raw in responses:
            if isinstance(raw, dict):
                raw = raw.get("text") or raw.get("content") or raw.get("completion") or ""
            text = str(raw) if raw is not None else ""
            sql = bridge.extract_sql(text)
            if not sql:
                continue

            parsed_sqls.append(sql)

            try:
                result = self.execute(sql)
            except Exception:
                continue

            if not result.get("ok"):
                continue

            rows = result.get("rows") or []
            key = self._result_key(rows)
            result_groups.setdefault(key, []).append(sql)
            successful_sqls.append(sql)

        if not successful_sqls:
            return parsed_sqls[0] if parsed_sqls else ""

        max_count = max(len(sqls) for sqls in result_groups.values())
        for group_sqls in result_groups.values():
            if len(group_sqls) == max_count:
                return group_sqls[0]

        return successful_sqls[0]

    @staticmethod
    def _row_key(row):
        if isinstance(row, (dict, list, tuple)):
            return json.dumps(row, sort_keys=True, default=str, separators=(",", ":"))
        return json.dumps(row, default=str)

    @classmethod
    def _result_key(cls, rows):
        row_keys = [cls._row_key(r) for r in rows]
        return repr(sorted(row_keys))