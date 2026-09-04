"""Harness that generates three independent SQL attempts, executes all that parse, and returns the SQL producing the majority execution result."""
from ..harness_base import SQLHarness
from .. import bridge
from collections import Counter

class P2P2DErnieS1Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        # Build prompt from schema and question
        prompt = f"{self.schema}\n\nQuestion: {question}\nSQL:"
        # Generate three independent SQL attempts with temperature 0.7
        attempts = self.llm(prompt, system="", temperature=0.7, n=3)
        # Ensure attempts is a list (if llm returns a single string for n=3, wrap it)
        if not isinstance(attempts, list):
            attempts = [attempts]
        
        valid_sql = []
        valid_results = []
        for attempt in attempts:
            sql = bridge.extract_sql(attempt)
            if not sql or not sql.strip():
                continue
            result = self.execute(sql)
            if result.get("ok", False):
                valid_sql.append(sql)
                rows = result.get("rows", [])
                # Convert rows to a hashable tuple for comparison
                try:
                    row_tuple = tuple(tuple(row) for row in rows)
                except TypeError:
                    row_tuple = tuple(rows)
                valid_results.append(row_tuple)
        
        if not valid_sql:
            return ""
        
        # Find majority execution result (appears at least twice)
        result_counts = Counter(valid_results)
        most_common_result, count = result_counts.most_common(1)[0]
        if count >= 2:
            for sql, res in zip(valid_sql, valid_results):
                if res == most_common_result:
                    return sql
        
        # If no majority result, find majority SQL string
        sql_counts = Counter(valid_sql)
        most_common_sql, sql_count = sql_counts.most_common(1)[0]
        if sql_count >= 2:
            return most_common_sql
        
        # Fallback: return the first valid SQL
        return valid_sql[0]