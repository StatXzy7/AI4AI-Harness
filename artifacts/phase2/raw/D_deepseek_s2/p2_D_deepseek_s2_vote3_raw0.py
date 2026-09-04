"""Ask the frozen solver for three SQL candidates, execute each, and return the SQL whose result set is the majority."""
import json

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Write a SQL query to answer the question.\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n"
            "Return only the SQL query."
        )

        raw_responses = self.llm(prompt, temperature=0.7, n=3)
        if isinstance(raw_responses, str):
            raw_responses = [raw_responses]
        elif raw_responses is None:
            raw_responses = []

        sql_candidates = []
        for raw in raw_responses:
            if not isinstance(raw, str):
                raw = str(raw)
            sql = bridge.extract_sql(raw)
            if sql:
                sql_candidates.append(sql)

        executed = []
        for sql in sql_candidates:
            result = self.execute(sql)
            if result.get("ok"):
                executed.append((sql, result.get("rows")))

        if not executed:
            return sql_candidates[0] if sql_candidates else ""

        def result_key(rows):
            if rows is None:
                return "null"
            items = rows if isinstance(rows, list) else [rows]
            serialized_items = []
            for item in items:
                try:
                    serialized_items.append(
                        json.dumps(item, sort_keys=True, default=str)
                    )
                except Exception:
                    serialized_items.append(repr(item))
            return json.dumps(sorted(serialized_items))

        groups = {}
        for sql, rows in executed:
            key = result_key(rows)
            groups.setdefault(key, []).append(sql)

        majority_key = max(groups, key=lambda k: len(groups[k]))
        return groups[majority_key][0]