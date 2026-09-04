"""Generates three independent SQL attempts via LLM, executes all that parse, and returns the majority result."""

from ..harness_base import SQLHarness
from .. import bridge
from collections import Counter

class P2P2DErnieS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        # Construct prompt with schema and question
        prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nWrite a SQL query to answer the question."
        
        # Generate 3 independent attempts with temperature 0.7
        responses = self.llm(prompt, system="", temperature=0.7, n=3)
        
        # Extract SQL from each response
        sqls = [bridge.extract_sql(r) for r in responses]
        
        # Execute each SQL and collect successful ones
        successful_sqls = []
        for sql in sqls:
            result = self.execute(sql)
            if result["ok"]:
                successful_sqls.append(sql)
        
        # If no successful executions, return empty string
        if not successful_sqls:
            return ""
        
        # Count frequencies and find majority
        counts = Counter(successful_sqls)
        max_count = max(counts.values())
        candidates = [sql for sql, cnt in counts.items() if cnt == max_count]
        
        # Return first candidate (preserves original attempt order for tie-breaking)
        return candidates[0]