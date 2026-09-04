# Two-stage SQL generation harness with execution-based refinement
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2BMinimaxS2G1(SQLHarness):
    """Two-stage harness: Stage 1 drafts an outline + SQL, Stage 2 refines against errors."""

    def solve(self, question: str) -> str:
        # ---------- Stage 1: draft ----------
        draft_prompt = (
            "You are a Text-to-SQL expert. Given the schema and question, "
            "first write a brief outline of the query plan, then write the SQL.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Outline:\n"
            "SQL:"
        )
        draft_text = self.llm(draft_prompt, system="", temperature=0.0, n=1)
        draft_sql = bridge.extract_sql(draft_text)

        # Try executing the draft; if it works, we're done.
        if draft_sql:
            result = self.execute(draft_sql)
            if result.get("ok"):
                return draft_sql

        # ---------- Stage 2: refine ----------
        # Build a refinement prompt that may include the previous error / output.
        prior_error = ""
        if draft_sql:
            prior_error = (
                f"Previous SQL:\n{draft_sql}\n"
                f"Execution error: {result.get('error', '')}\n"
                f"Rows (first 5): {result.get('rows', [])[:5]}\n"
            )

        refine_prompt = (
            "You are a Text-to-SQL expert. The previous attempt failed. "
            "Carefully diagnose the issue (wrong table, wrong join, "
            "wrong aggregation, schema misread, etc.) and produce a corrected SQL.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"{prior_error}\n"
            "Corrected SQL:"
        )
        refine_text = self.llm(refine_prompt, system="", temperature=0.0, n=1)
        refined_sql = bridge.extract_sql(refine_text)

        # Verify the refined SQL; if still broken, attempt a deterministic cleanup.
        if refined_sql:
            ok_result = self.execute(refined_sql)
            if ok_result.get("ok"):
                return refined_sql
            # One last fallback: strip trailing semicolons/whitespace and retry.
            cleaned = re.sub(r";\s*$", "", refined_sql).strip()
            if cleaned != refined_sql:
                final_check = self.execute(cleaned)
                if final_check.get("ok"):
                    return cleaned

        # Fall back to the refined SQL even if execution failed (best effort).
        return refined_sql or draft_sql or ""