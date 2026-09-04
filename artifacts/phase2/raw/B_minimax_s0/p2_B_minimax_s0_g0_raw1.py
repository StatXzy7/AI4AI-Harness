# Docstring: Two-stage harness that first drafts SQL with one prompt, then asks the LLM to refine it using the schema and original question as context.
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: initial greedy draft of SQL
        draft_prompt = (
            "You are a Text-to-SQL assistant.\n"
            "Given the database schema and a natural language question, "
            "produce a single SQL query that answers it.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return ONLY the SQL statement, no prose."
        )
        draft_raw = self.llm(draft_prompt, system="", temperature=0.0, n=1)
        draft_sql = bridge.extract_sql(draft_raw) or draft_raw.strip()

        # Stage 2: refinement pass. The earlier artifact (draft_sql) is consumed by
        # the second LLM call to produce a corrected/final SQL.
        refine_prompt = (
            "You are a Text-to-SQL refiner.\n"
            "You will be given a database schema, a natural language question, "
            "and a draft SQL query. Review the draft and produce a corrected, "
            "executable SQL query that faithfully answers the question.\n"
            "Ensure proper joins, filters, aggregations, and that referenced "
            "tables and columns exist in the schema.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Draft SQL:\n{draft_sql}\n\n"
            "Return ONLY the final SQL statement, no prose."
        )
        refined_raw = self.llm(refine_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(refined_raw) or refined_raw.strip()

        return final_sql