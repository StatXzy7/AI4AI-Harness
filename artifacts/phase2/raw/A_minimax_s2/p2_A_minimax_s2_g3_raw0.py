"""Two-stage harness where an earlier LLM stage analyzes the schema and question to produce a focused plan, then a later stage generates SQL from that plan."""
# MECHANISM: twostage

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        # --- Stage 1: produce a focused plan / intent sketch ---
        # Identify relevant tables/columns and the intent (which columns to select,
        # which filters/joints/aggregations to apply, expected shape of result).
        plan_prompt = (
            "You are analyzing a database schema and a natural-language question.\n"
            "Produce a CONCISE PLAN (no SQL) that will guide a later SQL-generation step.\n"
            "The plan must include:\n"
            "  1) Relevant tables and the specific columns needed from each.\n"
            "  2) Join keys (if multiple tables are needed).\n"
            "  3) Filter conditions (WHERE clauses) derived from the question.\n"
            "  4) Any aggregations, GROUP BY columns, or ORDER BY needed.\n"
            "  5) Any subtle interpretation decisions (e.g., 'most recent' -> ORDER BY ... LIMIT 1).\n"
            "Do NOT write SQL. Do NOT invent columns or tables that are not in the schema.\n"
            "Keep the plan under 15 short bullet points.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            "PLAN:"
        )
        plan_text = self.llm(plan_prompt, system="You are a precise SQL planning assistant.", temperature=0.0, n=1)

        # --- Stage 2: generate SQL conditioned on the plan ---
        sql_prompt = (
            "You are a Text-to-SQL generator. Given a database schema, a user question, "
            "and a focused PLAN, produce exactly one SQL query that answers the question.\n"
            "Follow the plan closely. Use only tables/columns present in the schema.\n"
            "Return ONLY the SQL (no prose, no markdown fences).\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            f"PLAN:\n{plan_text}\n\n"
            "SQL:"
        )
        raw_sql = self.llm(sql_prompt, system="You generate syntactically correct SQL.", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw_sql)

        # --- Lightweight validation: optional self-check refinement ---
        # If execution reveals an error, ask the model to fix it, using the original
        # plan and question as grounding context. This keeps the two-stage design
        # primary while adding a tiny repair fallback.
        probe = self.execute(sql)
        if not probe.get("ok", False):
            err = probe.get("error", "unknown error")
            repair_prompt = (
                "The following SQL was generated to answer the question but failed to execute. "
                "Fix it. Return ONLY the corrected SQL.\n\n"
                f"SCHEMA:\n{self.schema}\n\n"
                f"QUESTION:\n{question}\n\n"
                f"PLAN:\n{plan_text}\n\n"
                f"FAILED SQL:\n{sql}\n\n"
                f"EXECUTION ERROR:\n{err}\n\n"
                "CORRECTED SQL:"
            )
            fixed_raw = self.llm(repair_prompt, system="You fix SQL errors precisely.", temperature=0.0, n=1)
            sql = bridge.extract_sql(fixed_raw)

        return sql