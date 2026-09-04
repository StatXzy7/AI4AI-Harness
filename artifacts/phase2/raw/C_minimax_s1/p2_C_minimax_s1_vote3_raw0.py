"""3-way majority vote harness: samples 3 SQL attempts and returns the majority successful result."""
from collections import Counter
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS1Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        # Ask the weak solver for 3 independent SQL attempts
        prompt = f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nWrite a SQL query:"
        responses = self.llm(prompt, system="", temperature=0.7, n=3)

        # Collect parseable candidates and their execution results
        parsed_sqls = []
        for text in responses:
            sql = bridge.extract_sql(text)
            if sql:
                parsed_sqls.append(sql)

        # If nothing parsed, fall back to the first response's raw text
        if not parsed_sqls:
            return bridge.extract_sql(responses[0]) if responses else ""

        # Execute each candidate and tally the successful result sets
        successful_results = Counter()
        result_to_sql = {}
        fallback_sql = parsed_sqls[0]

        for sql in parsed_sqls:
            exec_result = self.execute(sql)
            if exec_result.get("ok"):
                # Use a frozenset of tuples as a hashable key for the result set
                key = frozenset(tuple(row) for row in exec_result.get("rows", []))
                successful_results[key] += 1
                result_to_sql.setdefault(key, sql)

        # Return the SQL corresponding to the majority result set
        if successful_results:
            majority_key = successful_results.most_common(1)[0][0]
            return result_to_sql[majority_key]

        # No successful execution: return the first parseable SQL as best-effort
        return fallback_sql