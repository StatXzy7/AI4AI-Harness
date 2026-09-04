"""Two-stage pipeline where first stage drafts SQL, executes it, and second stage repairs using execution feedback."""
# MECHANISM: twostage

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        # Stage 1: Generate an initial SQL draft from the question + schema
        draft_prompt = (
            f"You are an expert SQL writer. Given the schema below and the user's "
            f"question, write a single SQLite-compatible SQL query that answers it.\n\n"
            f"SCHEMA:\n{schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            f"Return ONLY the SQL query, nothing else. No markdown fences, no commentary."
        )
        draft_text = self.llm(draft_prompt, system="", temperature=0.0, n=1)
        draft_sql = bridge.extract_sql(draft_text) or draft_text.strip()

        # Execute the draft to gather runtime feedback
        result = self.execute(draft_sql)

        # If the draft works (and returns something), we may still refine in stage 2.
        # If it errors, stage 2 must repair.
        if result.get("ok") and result["rows"]:
            working_sql = draft_sql
            err_msg = ""
        elif result.get("ok") and not result["rows"]:
            working_sql = draft_sql
            err_msg = "Query executed but returned no rows."
        else:
            working_sql = draft_sql
            err_msg = result.get("error", "Unknown execution error")

        # Stage 2: Refine / repair based on execution feedback
        refine_prompt_parts = [
            "You are an expert SQL debugger and refiner.",
            "You will be given a schema, a natural-language question, an initial SQL draft, "
            "and execution feedback. Produce a corrected, improved SQLite-compatible SQL "
            "query that correctly answers the question.",
            "",
            "SCHEMA:",
            schema,
            "",
            "QUESTION:",
            question,
            "",
            "INITIAL_SQL:",
            working_sql,
            "",
        ]

        if err_msg:
            refine_prompt_parts.extend([
                "EXECUTION_ERROR:",
                err_msg,
                "",
                "Fix the SQL so it executes successfully and returns the expected result.",
                "",
            ])
        else:
            refine_prompt_parts.extend([
                "EXECUTION_RESULT:",
                "Query returned no rows.",
                "",
                "Rewrite the SQL to better answer the question. Consider alternative "
                "joins, filters, or column selections.",
                "",
            ])

        refine_prompt_parts.append(
            "Return ONLY the final SQL query. No markdown fences, no commentary."
        )
        refine_prompt = "\n".join(refine_prompt_parts)

        refined_text = self.llm(refine_prompt, system="", temperature=0.0, n=1)
        refined_sql = bridge.extract_sql(refined_text) or refined_text.strip()

        # Validate the refined query; if it's broken, fall back to the working draft.
        final_check = self.execute(refined_sql)
        if final_check.get("ok"):
            return refined_sql

        # Last-resort fallback: try the original draft once more
        return working_sql