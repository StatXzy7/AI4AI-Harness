"""Draw multiple samples and choose the most frequent executable SQL query."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BDeepseekS0G4(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n"
            "Write a SQL query that answers the question. Only output the SQL query."
        )
        samples = self.llm(prompt, system="", temperature=0.7, n=5)
        if isinstance(samples, str):
            samples = [samples]

        # Extract candidate SQL strings
        candidates = []
        for sample in samples:
            if not isinstance(sample, str):
                sample = str(sample)
            sql = bridge.extract_sql(sample)
            if sql:
                candidates.append(sql)
        if not candidates:
            return ""

        # Deduplicate while preserving order
        unique = list(dict.fromkeys(candidates))

        # Identify candidates that execute successfully and return rows
        successful = []
        for sql in unique:
            try:
                result = self.execute(sql)
                if result.get("ok") and result.get("rows"):
                    successful.append(sql)
            except Exception:
                pass

        # Use successful candidates if any, else all unique candidates
        pool = successful if successful else unique

        # Count occurrences in the original candidate list
        counts = {sql: candidates.count(sql) for sql in pool}

        # Choose the SQL with the highest count; break ties by earliest appearance
        max_count = max(counts.values())
        for sql in pool:
            if counts[sql] == max_count:
                return sql

        # Fallback (should never be reached)
        return pool[0]