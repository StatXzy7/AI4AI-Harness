"""Executes three independent SQL generations and returns the majority result among those that parse."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a SQL query to answer the question."
        responses = self.llm(prompt, system="", temperature=0.7, n=3)
        successful_sqls = []
        for text in responses:
            sql = bridge.extract_sql(text)
            if sql:  # ignore empty extractions
                result = self.execute(sql)
                if result["ok"]:
                    successful_sqls.append(sql)
        if not successful_sqls:
            return ""
        # Count occurrences and pick the majority (first encountered in case of tie)
        counts = {}
        for sql in successful_sqls:
            counts[sql] = counts.get(sql, 0) + 1
        majority_sql = max(counts, key=counts.get)
        return majority_sql