"""Schema-aware two-stage SQL harness that drafts a query then refines it with execution feedback."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS1G6(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: draft an initial SQL proposal guided by the schema.
        draft_prompt = (
            "You are a careful Text-to-SQL generator.\n"
            "Given the database schema below and the user's question, write a single SQLite SQL "
            "query that answers it. Output ONLY the SQL statement — no explanation, no markdown.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        draft_text = self.llm(draft_prompt, system="", temperature=0.0, n=1)
        candidate = bridge.extract_sql(draft_text)
        if not candidate:
            candidate = draft_text.strip().strip("`").strip()

        # Stage 2: iteratively repair by feeding execution feedback back to the LLM.
        max_attempts = 3
        for attempt in range(max_attempts):
            exec_result = self.execute(candidate)
            if exec_result.get("ok"):
                return candidate

            error_msg = exec_result.get("error") or "unknown execution error"
            rows = exec_result.get("rows")

            # If execution succeeded but returned unexpected rows, still attempt a repair once.
            if attempt == 0 and rows is not None and len(rows) == 0:
                repair_prompt = (
                    "You are debugging a SQL query that executed without error but returned zero rows.\n"
                    "The schema and question are below, along with the query. Rewrite the query so it "
                    "returns the expected non-empty result. Output ONLY the corrected SQL.\n\n"
                    f"Schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Previous SQL:\n{candidate}\n\n"
                    "Corrected SQL:"
                )
            else:
                repair_prompt = (
                    "You are debugging a failing SQL query.\n"
                    "The schema, question, query, and database error are below. Rewrite the query so "
                    "it executes successfully and answers the question. Output ONLY the corrected SQL.\n\n"
                    f"Schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Previous SQL:\n{candidate}\n\n"
                    f"Database error:\n{error_msg}\n\n"
                    "Corrected SQL:"
                )

            repaired_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            repaired = bridge.extract_sql(repaired_text)
            if not repaired:
                repaired = repaired_text.strip().strip("`").strip()
            if repaired == candidate:
                # Model produced no change; stop to avoid an infinite loop.
                break
            candidate = repaired

        # Final verification pass — return whatever currently executes (even if it errors,
        # the harness can decide how to surface that).
        final_result = self.execute(candidate)
        return candidate if final_result.get("ok") else candidate