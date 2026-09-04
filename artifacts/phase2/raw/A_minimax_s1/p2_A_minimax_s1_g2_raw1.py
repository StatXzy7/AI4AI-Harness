"""Two-stage harness: first stage drafts SQL via a planner prompt, second stage critiques and refines it using schema knowledge."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS1G2(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: planning + draft
        plan_system = (
            "You are a SQL planning assistant. Given a database schema and a natural "
            "language question, produce a brief plan describing which tables and columns "
            "are needed, the relevant joins, and any filters. Then write a single SQL "
            "query that answers the question. Output the plan, then a line '--- SQL ---', "
            "then the SQL."
        )
        plan_prompt = f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nPlan and SQL:"
        stage1 = self.llm(plan_prompt, system=plan_system, temperature=0.0, n=1)
        draft_sql = bridge.extract_sql(stage1)
        if not draft_sql:
            draft_sql = stage1.strip()

        # Stage 2: critique + refinement
        refine_system = (
            "You are a SQL reviewer. You will be given a database schema, a question, "
            "and a candidate query. Check the candidate for correctness against the "
            "schema: proper table/column names, correct JOIN logic, correct aggregation, "
            "and that it addresses what the question wants. If the candidate is correct, "
            "return it unchanged. If it has errors, return the fixed SQL. Provide the "
            "final SQL after a line '--- SQL ---'."
        )
        refine_prompt = (
            f"Schema:\n{self.schema}\n\nQuestion: {question}\n\n"
            f"Candidate SQL:\n{draft_sql}\n\n"
            "Critique and return the final SQL:"
        )
        stage2 = self.llm(refine_prompt, system=refine_system, temperature=0.0, n=1)
        final_sql = bridge.extract_sql(stage2)
        if not final_sql:
            final_sql = stage1.strip()

        return final_sql