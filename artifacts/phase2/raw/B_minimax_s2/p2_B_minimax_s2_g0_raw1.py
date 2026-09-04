"""P2P2BMinimaxS2G0: Two-stage harness where the first stage produces a column-grounded plan, and the second stage generates SQL conditioned on that plan, with execution feedback used to repair invalid SQL."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: produce a plan mentioning relevant tables/columns from the schema
        plan_prompt = (
            "Given the database schema below, identify the minimal subset of tables and "
            "columns needed to answer the user's question. Output a short plan: list the "
            "relevant table names, the relevant column names, any necessary joins, and any "
            "filters or aggregations implied. Do not write SQL. Do not include any "
            "explanation beyond the plan itself.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Plan:"
        )
        plan_text = self.llm(plan_prompt, system="", temperature=0.0, n=1).strip()
        if not plan_text:
            plan_text = "Use the schema as needed to answer the question."

        # Stage 2: generate SQL conditioned on the plan
        sql_prompt = (
            "Write a single SQLite-compatible SQL query that answers the question. "
            "Follow the provided plan. Use only tables and columns mentioned in the "
            "plan or the schema. Output ONLY the SQL query, with no commentary, no "
            "markdown fences, and no trailing text.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Plan:\n{plan_text}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )

        max_repair_iters = 2
        last_sql = ""
        last_error = ""

        for attempt in range(max_repair_iters + 1):
            if attempt == 0:
                raw = self.llm(sql_prompt, system="", temperature=0.0, n=1)
            else:
                repair_prompt = (
                    sql_prompt
                    + "\n\nYour previous SQL failed to execute with this error:\n"
                    + (last_error or "unknown error")
                    + "\n\nFix the SQL and output only the corrected query."
                )
                raw = self.llm(repair_prompt, system="", temperature=0.0, n=1)

            candidate = bridge.extract_sql(raw).strip()
            if not candidate:
                candidate = raw.strip()
            last_sql = candidate

            result = self.execute(candidate)
            if result.get("ok"):
                return candidate

            last_error = result.get("error", "") or "unknown execution error"
            # If execution produced rows, accept even on minor warnings
            if result.get("rows") is not None and not result.get("error"):
                return candidate

        return last_sql