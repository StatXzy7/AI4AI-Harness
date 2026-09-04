"""A Text-to-SQL harness that generates, executes, repairs on error, and falls back to plan-then-generate."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G2(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        max_repairs = 3
        last_non_empty_sql = ""

        # Stage 1: direct SQL generation
        initial_prompt = (
            "You are a SQLite expert. Write a single SQL query that answers the question.\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query, no explanation."
        )
        sql = self._generate_sql(initial_prompt)
        if sql:
            last_non_empty_sql = sql
        result = self._safe_execute(sql)
        if result is not None and result.get("ok"):
            return sql

        previous_sql = sql

        # Stage 2: error-driven repair loop
        for attempt in range(1, max_repairs + 1):
            if result is None:
                error = "No SQL was generated in the previous step."
            elif not result.get("ok"):
                error = result.get("error", "Unknown execution error")
            else:
                error = "Query executed successfully but returned zero rows."

            repair_prompt = (
                "The previous SQL attempt for the question was not satisfactory.\n"
                f"Schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                f"Previous SQL:\n{previous_sql}\n\n"
                f"Error:\n{error}\n\n"
                "Write a corrected SQLite query. Return only the SQL query, no explanation."
            )
            sql = self._generate_sql(repair_prompt)
            if not sql:
                sql = previous_sql
            else:
                last_non_empty_sql = sql

            result = self._safe_execute(sql)
            if result is not None and result.get("ok"):
                return sql
            previous_sql = sql

        # Stage 3: plan-then-generate fallback
        plan_prompt = (
            "You are a SQL expert. Before writing SQL, write a short plain-English plan for the query.\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Plan:"
        )
        plan_raw = self.llm(plan_prompt, system="", temperature=0.0, n=1)
        plan = plan_raw if isinstance(plan_raw, str) else "\n".join(map(str, plan_raw))

        plan_to_sql_prompt = (
            "Use the plan to write a single SQLite query.\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan}\n\n"
            "Return only the SQL query, no explanation."
        )
        sql = self._generate_sql(plan_to_sql_prompt)
        if sql:
            last_non_empty_sql = sql
        result = self._safe_execute(sql)
        if result is not None and result.get("ok"):
            return sql

        # Stage 4: final constrained direct attempt
        final_prompt = (
            "Carefully read the schema. Use only tables, columns, and SQL syntax that are valid for SQLite.\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query. Return only the SQL query."
        )
        sql = self._generate_sql(final_prompt)
        if not sql:
            return last_non_empty_sql or previous_sql
        return sql

    def _generate_sql(self, prompt: str) -> str:
        raw = self.llm(prompt, system="", temperature=0.0, n=1)
        text = raw if isinstance(raw, str) else "\n".join(map(str, raw))
        return bridge.extract_sql(text)

    def _safe_execute(self, sql: str):
        if not sql:
            return None
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}