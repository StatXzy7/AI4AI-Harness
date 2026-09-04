"""Generates three SQL candidates, executes the parsed ones, and returns the SQL producing the most common successful result set."""

import json

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Given the following database schema:\n"
            f"{self.schema}\n\n"
            "Write a SQL query to answer the question. Return only the SQL query, no explanation.\n\n"
            f"Question: {question}\n"
        )

        completions = self.llm(prompt, system="", temperature=0.7, n=3)
        if completions is None:
            completions = []
        elif isinstance(completions, str):
            completions = [completions]
        else:
            completions = list(completions)

        parsed_sqls = []
        for completion in completions:
            sql = bridge.extract_sql(completion)
            if sql:
                parsed_sqls.append(sql)

        if not parsed_sqls:
            return ""

        first_sql = parsed_sqls[0]
        successful = []

        for sql in parsed_sqls:
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if result.get("ok"):
                rows = result.get("rows", [])
                try:
                    key = json.dumps(rows, sort_keys=True, default=str)
                except Exception:
                    key = repr(rows)
                successful.append((sql, key))

        if successful:
            counts = {}
            order = []
            for _, key in successful:
                if key not in counts:
                    counts[key] = 0
                    order.append(key)
                counts[key] += 1

            majority_key = max(order, key=lambda k: counts[k])
            for sql, key in successful:
                if key == majority_key:
                    return sql

        return first_sql