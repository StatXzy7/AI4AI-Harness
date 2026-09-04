"""Two-stage harness where the first stage drafts an SQL plan and the second stage writes SQL from it."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        plan_prompt = (
            "You are designing a query plan against the schema below.\n"
            "Schema:\n{schema}\n\n"
            "Question: {q}\n\n"
            "List, in plain text, the minimal steps needed to answer the question:\n"
            "1. Which tables and joins are required.\n"
            "2. Which columns are selected or filtered.\n"
            "3. Any aggregates, group-by, or order-by.\n"
            "4. Any subqueries or CTE structure.\n"
            "Do NOT write SQL. Output only the numbered plan."
        ).format(schema=self.schema, q=question)

        plan = self.llm(plan_prompt, system="You are a precise query planner.", temperature=0.0, n=1).strip()

        sql_prompt = (
            "Schema:\n{schema}\n\n"
            "Question: {q}\n\n"
            "Approved plan:\n{plan}\n\n"
            "Write a single SQLite-compatible SQL statement that exactly implements the plan above.\n"
            "Rules:\n"
            "- Use only tables/columns present in the schema.\n"
            "- Prefer explicit JOIN ... ON syntax.\n"
            "- Do not wrap the SQL in markdown or commentary.\n"
            "SQL:"
        ).format(schema=self.schema, q=question, plan=plan)

        draft = self.llm(sql_prompt, system="You translate plans into correct SQL.", temperature=0.0, n=1)
        sql = bridge.extract_sql(draft)

        # Verification loop: if execution fails, re-prompt using plan + error feedback once.
        exec_result = self.execute(sql)
        if not exec_result.get("ok", False):
            error = exec_result.get("error", "unknown error")
            repair_prompt = (
                "Your previous SQL failed to execute.\n"
                "Schema:\n{schema}\n\n"
                "Question: {q}\n\n"
                "Plan:\n{plan}\n\n"
                "Previous SQL:\n{sql}\n\n"
                "Error:\n{err}\n\n"
                "Produce a corrected SQLite SQL statement. Output only the SQL."
            ).format(schema=self.schema, q=question, plan=plan, sql=sql, err=error)
            repaired = self.llm(repair_prompt, system="You fix SQL that fails to execute.", temperature=0.0, n=1)
            sql = bridge.extract_sql(repaired)

        return sql