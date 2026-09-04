"""Prompt-to-prompt dual-formulation harness that executes two independent SQL candidates and returns the non-empty result."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # First formulation: join-based query
        join_prompt = (
            "You are a SQL expert. Given the schema and the user's question, "
            "produce exactly one valid SQL statement using explicit JOIN syntax "
            "to combine relevant tables. Output only the SQL, no prose.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\nSQL:"
        )
        join_text = self.llm(join_prompt, system="", temperature=0.0, n=1)
        join_sql = bridge.extract_sql(join_text)

        # Second formulation: subquery-based query (independent reformulation)
        subq_prompt = (
            "You are a SQL expert. Given the schema and the user's question, "
            "produce exactly one valid SQL statement that solves the question "
            "using nested subqueries (SELECT within WHERE/FROM) rather than "
            "explicit JOINs. Output only the SQL, no prose.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\nSQL:"
        )
        subq_text = self.llm(subq_prompt, system="", temperature=0.0, n=1)
        subq_sql = bridge.extract_sql(subq_text)

        # Execute both candidates
        join_result = self.execute(join_sql) if join_sql else {"ok": False, "rows": [], "error": "no sql"}
        subq_result = self.execute(subq_sql) if subq_sql else {"ok": False, "rows": [], "error": "no sql"}

        # Selection rule: prefer non-empty; if both non-empty, return the first
        if join_result.get("ok") and len(join_result.get("rows", [])) > 0:
            return join_sql
        if subq_result.get("ok") and len(subq_result.get("rows", [])) > 0:
            return subq_sql

        # Both empty or both failed: return the first candidate as fallback
        return join_sql if join_sql else (subq_sql or "")