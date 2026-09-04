"""Generates 3 independent SQL attempts via LLM, executes valid ones, and returns the majority SQL string."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        # Build prompt requesting 3 independent SQL attempts
        prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Generate 3 independent SQL queries that answer the question. "
            f"Return each query on a separate line."
        )
        
        # Get 3 independent attempts with temperature 0.7
        attempts = self.llm(prompt, system="", temperature=0.7, n=3)
        
        # Extract SQL from each attempt and track valid ones
        valid_sqls = []
        for text in attempts:
            sql = bridge.extract_sql(text)
            if sql:
                result = self.execute(sql)
                if result["ok"]:
                    valid_sqls.append(sql)
        
        # If no valid SQLs, return empty string
        if not valid_sqls:
            return ""
        
        # Count frequencies and find majority
        freq = {}
        for sql in valid_sqls:
            freq[sql] = freq.get(sql, 0) + 1
        
        # Find SQL with highest frequency (majority)
        majority_sql = max(freq.items(), key=lambda x: x[1])[0]
        return majority_sql