"""Generates three independent SQL attempts via LLM, executes those that parse, and returns the majority SQL string."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS0Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        # Construct prompt for the weak solver
        prompt = f"Given the schema: {self.schema}\nQuestion: {question}\nGenerate SQL to answer the question."
        # Get three independent attempts with temperature 0.7
        responses = self.llm(prompt, system="", temperature=0.7, n=3)
        extracted_sqls = []
        results = []  # list of (sql, ok, rows, error)
        for text in responses:
            sql = bridge.extract_sql(text)
            extracted_sqls.append(sql)
            # Execute the extracted SQL; self.execute returns a dict
            result = self.execute(sql)
            results.append((sql, result["ok"], result["rows"], result["error"]))
        # Filter to only successfully parsed/executed queries
        successful = [(sql, ok, rows, err) for sql, ok, rows, err in results if ok]
        if not successful:
            # Fallback: return the first extracted SQL even if it failed
            return extracted_sqls[0] if extracted_sqls else ""
        # Count frequencies of SQL strings among successful attempts
        freq = {}
        for sql, _, _, _ in successful:
            freq[sql] = freq.get(sql, 0) + 1
        # Find SQL with highest frequency
        majority_sql = max(freq, key=freq.get)
        # If there is a clear majority (count >= 2), return it; otherwise return the first successful SQL
        if freq[majority_sql] >= 2:
            return majority_sql
        else:
            # All successful SQLs are distinct; return the first one
            return successful[0][0]