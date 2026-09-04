"""Voting harness that asks the solver for 3 independent SQL attempts and returns the majority executable result."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS0Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = f"Given the following schema:\n{self.schema}\n\nWrite a SQL query to answer: {question}"
        
        # Get 3 independent SQL attempts
        responses = self.llm(prompt, system="", temperature=0.7, n=3)
        
        # Extract and validate SQL from each response
        valid_sqls = []
        for response in responses:
            sql = bridge.extract_sql(response)
            if sql:
                result = self.execute(sql)
                if result.get("ok"):
                    valid_sqls.append(sql)
        
        # Return majority vote, or first valid SQL if no clear majority
        if not valid_sqls:
            return ""
        
        # Count occurrences and return the majority
        from collections import Counter
        sql_counts = Counter(valid_sqls)
        most_common = sql_counts.most_common(1)[0]
        return most_common[0]