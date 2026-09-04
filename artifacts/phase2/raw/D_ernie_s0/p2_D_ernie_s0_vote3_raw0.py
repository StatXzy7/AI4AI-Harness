"""Harness that generates 3 independent SQL attempts via LLM, executes each, and returns the majority successful query."""
from ..harness_base import SQLHarness
from .. import bridge
from collections import Counter

class P2P2DErnieS0Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        # Build prompt with schema and question
        prompt = f"Schema: {self.schema}\nQuestion: {question}\nSQL:"
        
        # Generate 3 independent SQL attempts with temperature=0.7
        responses = self.llm(prompt, system="", temperature=0.7, n=3)
        
        successful_sqls = []
        for response in responses:
            # Extract SQL from the response text
            sql = bridge.extract_sql(response)
            # Execute the SQL and check if it's valid
            result = self.execute(sql)
            if result.get("ok", False):
                successful_sqls.append(sql)
        
        # If no successful queries, return empty string
        if not successful_sqls:
            return ""
        
        # Count occurrences of each SQL string
        sql_counts = Counter(successful_sqls)
        # Get the most common SQL (majority vote)
        most_common_sql, _ = sql_counts.most_common(1)[0]
        return most_common_sql