"""Two-stage harness: first draft SQL, then critique-and-rewrite before execution."""
# MECHANISM: twostage

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        # ---- Stage 1: initial greedy generation of a candidate SQL ----
        stage1_prompt = (
            "You are a careful Text-to-SQL generator.\n"
            "Given the database schema below and the user's question, "
            "produce ONE single SQLite SQL query that answers it.\n"
            "Return ONLY the SQL, no prose, no markdown fences.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        stage1_output = self.llm(stage1_prompt, system="", temperature=0.0, n=1)
        candidate_sql = bridge.extract_sql(stage1_output).strip()
        if not candidate_sql:
            candidate_sql = stage1_output.strip()

        # Always feed SOMETHING into stage 2; if the draft was empty, use a
        # explicit placeholder so the reviser still produces output.
        draft_for_revision = candidate_sql or "SELECT 1"

        # ---- Stage 2: critique + revise the candidate against the schema ----
        stage2_prompt = (
            "You are a senior SQLite reviewer. You will be given a database "
            "schema, a natural-language question, and a DRAFT SQL query that "
            "attempts to answer it. Your job is to produce a CORRECTED SQL "
            "query that is more likely to execute and to answer the question.\n\n"
            "Check specifically for:\n"
            "  - correct referenced tables and columns actually present in the schema\n"
            "  - correct JOIN keys and join direction\n"
            "  - correct use of GROUP BY / aggregates / filters\n"
            "  - no hallucinated columns or tables\n"
            "  - syntactically valid SQLite\n\n"
            "Return ONLY the final corrected SQL, no prose, no markdown fences.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Draft SQL:\n{draft_for_revision}\n\n"
            "Corrected SQL:"
        )
        stage2_output = self.llm(stage2_prompt, system="", temperature=0.0, n=1)
        revised_sql = bridge.extract_sql(stage2_output).strip()
        if not revised_sql:
            revised_sql = stage2_output.strip()

        # Prefer the stage-2 revised SQL; fall back to stage-1 draft if stage-2
        # somehow produced nothing usable.
        final_sql = revised_sql or candidate_sql or "SELECT 1"

        # Sanity check: if the chosen SQL doesn't even parse/execute, degrade
        # to the other candidate rather than returning broken output.
        try:
            check = self.execute(final_sql)
            if not check.get("ok", False):
                fallback = revised_sql if final_sql is candidate_sql else candidate_sql
                if fallback:
                    fb_check = self.execute(fallback)
                    if fb_check.get("ok", False):
                        final_sql = fallback
        except Exception:
            # If execute itself raises, just return the SQL we have.
            pass

        return final_sql