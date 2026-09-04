"""P2P2CMinimaxS0TwoView: Generate two independent SQL formulations (join-based and subquery-based), execute both, and return the non-empty result or the first one if both succeed."""
import json
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS0TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        final_sql = ""

        # ---------- Attempt 1: Join-based formulation ----------
        join_system = (
            "You write SQL using explicit JOIN syntax. Output only the SQL query, no prose, no markdown fences."
        )
        join_prompt = (
            f"Given the database schema below, write a SQL query that answers the question using explicit JOINs "
            f"(INNER JOIN, LEFT JOIN, etc.).\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"SQL:"
        )
        join_text = self.llm(join_prompt, system=join_system, temperature=0.0, n=1)
        join_sql = bridge.extract_sql(join_text)

        join_result = self.execute(join_sql) if join_sql else {"ok": False, "rows": [], "error": "empty_sql"}

        # ---------- Attempt 2: Subquery-based formulation ----------
        sub_system = (
            "You write SQL using subqueries (IN, EXISTS, scalar subqueries) instead of joins where possible. "
            "Output only the SQL query, no prose, no markdown fences."
        )
        sub_prompt = (
            f"Given the database schema below, write a SQL query that answers the question primarily using subqueries "
            f"(e.g., WHERE x IN (SELECT ...), WHERE EXISTS (...)) rather than explicit JOINs.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"SQL:"
        )
        sub_text = self.llm(sub_prompt, system=sub_system, temperature=0.0, n=1)
        sub_sql = bridge.extract_sql(sub_text)

        sub_result = self.execute(sub_sql) if sub_sql else {"ok": False, "rows": [], "error": "empty_sql"}

        # ---------- Selection rule: non-empty wins, else first that ran ok ----------
        join_has_rows = bool(join_result.get("ok")) and len(join_result.get("rows", [])) > 0
        sub_has_rows = bool(sub_result.get("ok")) and len(sub_result.get("rows", [])) > 0

        if join_has_rows and not sub_has_rows:
            final_sql = join_sql
        elif sub_has_rows and not join_has_rows:
            final_sql = sub_sql
        elif join_has_rows and sub_has_rows:
            # tie-breaker: prefer the join-based formulation
            final_sql = join_sql
        else:
            # Neither returned rows. Fall back to whichever query at least executed
            # without an error; if both errored (or were empty), prefer the join one.
            if bool(join_result.get("ok")):
                final_sql = join_sql
            elif bool(sub_result.get("ok")):
                final_sql = sub_sql
            else:
                final_sql = join_sql if join_sql else sub_sql

        return final_sql