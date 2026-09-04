"""Generates two SQL formulations (join-based and subquery-based), executes both, and returns the SQL that yields non-empty results (first if both do)."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2DDeepseekS1TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # System instruction to encourage SQL-only output
        system_msg = "You are a SQL expert. Output only the SQL query without any explanation."

        # Prompt 1: join-based formulation
        join_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Write a SQL query to answer the question using JOIN operations. "
            "Use explicit JOIN syntax and avoid subqueries if possible."
        )

        # Prompt 2: subquery-based formulation
        subquery_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Write a SQL query to answer the question using subqueries "
            "(e.g., IN, EXISTS, scalar subqueries) where appropriate. "
            "Prefer a subquery-based approach over joins."
        )

        # Call LLM for both formulations (temperature=0.0 for determinism)
        raw1 = self.llm(join_prompt, system=system_msg, temperature=0.0, n=1)
        raw2 = self.llm(subquery_prompt, system=system_msg, temperature=0.0, n=1)

        # Extract first completion from possible list/string
        text1 = raw1[0] if isinstance(raw1, list) and raw1 else raw1
        text2 = raw2[0] if isinstance(raw2, list) and raw2 else raw2

        # Extract SQL from LLM responses
        sql1 = bridge.extract_sql(text1)
        sql2 = bridge.extract_sql(text2)

        # Execute both candidate SQL queries
        res1 = self.execute(sql1)
        res2 = self.execute(sql2)

        # Helper to decide if a result is "non-empty" (executed OK and has rows)
        def is_non_empty(res):
            return res.get("ok", False) and len(res.get("rows", [])) > 0

        # Control flow: choose first if it is non-empty; else second if non-empty; else fallback to first
        if is_non_empty(res1):
            return sql1
        elif is_non_empty(res2):
            return sql2
        else:
            return sql1