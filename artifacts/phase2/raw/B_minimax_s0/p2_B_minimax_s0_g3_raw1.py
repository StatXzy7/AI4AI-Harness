"""Repair harness: execute generated SQL and feed errors back for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        initial_sql = self._generate_initial_sql(question)
        final_sql = self._repair_loop(question, initial_sql)
        return final_sql

    def _generate_initial_sql(self, question: str) -> str:
        prompt = self._build_initial_prompt(question)
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        return bridge.extract_sql(response)

    def _build_initial_prompt(self, question: str) -> str:
        return (
            "You are a SQL expert. Given the schema below and a natural language "
            "question, write a single SQL query that answers the question.\n\n"
            "Return ONLY the SQL inside a