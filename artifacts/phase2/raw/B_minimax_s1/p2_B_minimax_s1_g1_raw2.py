"""Two-stage SQL generation: first stage extracts query constraints, second stage produces SQL conditioned on them."""
# MECHANISM: twostage    -- an earlier LLM stage produces an artifact a later stage consumes
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2BMinimaxS1G1(SQLHarness):
    """Harness that decomposes Text-to-SQL into a constraint-extraction stage and a SQL-synthesis stage."""

    def solve(self, question: str) -> str:
        # ---- Stage 1: Extract structured query constraints ----
        stage1_prompt = (
            "You are an expert at analyzing natural-language database questions.\n"
            "Given a database schema and a user question, identify the key query constraints.\n"
            "Schema:\n" + self.schema + "\n\n"
            "Question: " + question + "\n\n"
            "List the following constraints in a concise, numbered list:\n"
            "1. TABLES: which tables are involved\n"
            "2. COLUMNS: which columns are selected or filtered on\n"
            "3. FILTERS: WHERE-clause predicates (column, operator, value)\n"
            "4. AGGREGATIONS: any GROUP BY, HAVING, or aggregate functions\n"
            "5. JOINS: how tables relate (join keys)\n"
            "6. ORDERING: any ORDER BY / LIMIT requirements\n"
            "Be specific and reference actual column and table names from the schema."
        )

        constraints = self.llm(stage1_prompt, system="You extract precise query constraints.", temperature=0.0, n=1)

        # ---- Stage 2: Synthesize SQL conditioned on the constraints ----
        stage2_prompt = (
            "You are an expert SQL generator.\n"
            "Schema:\n" + self.schema + "\n\n"
            "Question: " + question + "\n\n"
            "Extracted query constraints:\n" + constraints + "\n\n"
            "Write a single SQLite-compatible SQL query that answers the question.\n"
            "Use the constraints above as your specification.\n"
            "Return ONLY the SQL inside a