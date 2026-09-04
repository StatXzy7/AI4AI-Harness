"""Ask the frozen solver for three independent SQL attempts at temperature 0.7, execute all parseable queries, and return the SQL whose result set wins a majority vote."""
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS1Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Use the following database schema to answer the question with a single SQL query.\n"
            "Do not include any explanation, only the SQL query.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )

        raw_responses = self.llm(prompt, system="", temperature=0.7, n=3)
        if isinstance(raw_responses, str):
            raw_responses = [raw_responses]
        elif raw_responses is None:
            raw_responses = []

        sqls = []
        for response in raw_responses:
            sql = bridge.extract_sql(response or "")
            if sql:
                sqls.append(sql.strip())

        if not sqls:
            return ""

        executed = []
        for sql in sqls:
            try:
                result = self.execute(sql)
            except Exception:
                continue
            if isinstance(result, dict) and result.get("ok"):
                executed.append((sql, result.get("rows", [])))

        if not executed:
            return sqls[0]

        def canonical(rows):
            canon = []
            for row in rows:
                if isinstance(row, dict):
                    canon.append(tuple(sorted(row.items())))
                elif isinstance(row, (list, tuple)):
                    canon.append(tuple(row))
                else:
                    canon.append(row)
            try:
                canon.sort(key=repr)
            except Exception:
                pass
            return canon

        counts = Counter(repr(canonical(rows)) for _, rows in executed)

        best_sql = None
        best_count = -1
        for sql, rows in executed:
            cnt = counts[repr(canonical(rows))]
            if cnt > best_count:
                best_count = cnt
                best_sql = sql

        return best_sql if best_sql is not None else executed[0][0]