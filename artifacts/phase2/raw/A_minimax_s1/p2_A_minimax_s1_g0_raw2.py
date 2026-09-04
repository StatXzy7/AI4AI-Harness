"""Two-stage Text-to-SQL: first LLM drafts a logical plan, second LLM converts plan + schema into executable SQL."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


PLANNER_SYSTEM = (
    "You are a senior data analyst. Given a natural language question and a database schema, "
    "produce a concise, step-by-step logical plan describing HOW to answer the question in SQL. "
    "Do NOT write SQL itself. Focus on: which tables/columns are needed, which joins, which "
    "filters (conditions), which groupings/aggregations, and which ordering/limits. "
    "Output ONLY the numbered plan, nothing else."
)


SQL_SYSTEM = (
    "You are an expert SQL writer. Given a database schema, a natural language question, and a "
    "logical plan, write a SINGLE executable SQL query that answers the question. Output ONLY the "
    "SQL statement, no prose, no markdown fences."
)


REPAIR_SYSTEM = (
    "You are an expert SQL debugger. The previous SQL query failed to execute against the database. "
    "Given the schema, the natural language question, the logical plan, and the error message, "
    "produce a corrected SQL query. Output ONLY the corrected SQL, no prose, no fences."
)


class P2P2AMinimaxS1G0(SQLHarness):

    # ---------- helper: clean LLM text -> SQL ----------
    @staticmethod
    def _sql_only(text: str) -> str:
        if text is None:
            return ""
        s = bridge.extract_sql(text) or ""
        if not s.strip():
            # fallback: try to grab anything after the last fenced block, else first line with SELECT/WITH/INSERT/UPDATE/DELETE
            s2 = text.strip()
            # crude: take the longest line containing a SQL keyword
            best = ""
            for line in s2.splitlines():
                up = line.strip().upper()
                if any(up.startswith(k) for k in ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "CREATE")):
                    if len(line) > len(best):
                        best = line.strip()
            s = best
        return s.strip()

    # ---------- stage 1: planner ----------
    def _make_plan(self, question: str) -> str:
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Logical plan (numbered steps, no SQL):"
        )
        out = self.llm(prompt, system=PLANNER_SYSTEM, temperature=0.0, n=1)
        # `out` may be a string or list-of-strings depending on harness
        if isinstance(out, list):
            out = out[0] if out else ""
        return (out or "").strip()

    # ---------- stage 2: SQL writer ----------
    def _draft_sql(self, question: str, plan: str) -> str:
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan}\n\n"
            f"SQL query:"
        )
        out = self.llm(prompt, system=SQL_SYSTEM, temperature=0.0, n=1)
        if isinstance(out, list):
            out = out[0] if out else ""
        return self._sql_only(out or "")

    # ---------- repair turn ----------
    def _repair_sql(self, question: str, plan: str, prev_sql: str, error: str) -> str:
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan}\n\n"
            f"Previous SQL:\n{prev_sql}\n\n"
            f"Execution error:\n{error}\n\n"
            f"Corrected SQL:"
        )
        out = self.llm(prompt, system=REPAIR_SYSTEM, temperature=0.0, n=1)
        if isinstance(out, list):
            out = out[0] if out else ""
        return self._sql_only(out or "")

    # ---------- public entry ----------
    def solve(self, question: str) -> str:
        # Stage 1: produce a logical plan
        plan = self._make_plan(question)
        if not plan:
            # if planner fails, fall back to an empty plan (stage 2 must still try)
            plan = ""

        # Stage 2: turn the plan into SQL
        sql = self._draft_sql(question, plan)
        if not sql:
            # last-resort: ask the LLM directly with no plan
            prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"SQL query:"
            )
            out = self.llm(prompt, system="You write correct, executable SQL. Output only SQL.",
                           temperature=0.0, n=1)
            if isinstance(out, list):
                out = out[0] if out else ""
            sql = self._sql_only(out or "")

        if not sql:
            return ""

        # Lightweight repair loop: at most 2 attempts if execution fails
        for _ in range(2):
            res = self.execute(sql)
            if res and res.get("ok"):
                return sql
            err = (res or {}).get("error", "") or "unknown execution error"
            new_sql = self._repair_sql(question, plan, sql, err)
            if not new_sql or new_sql.strip() == sql.strip():
                break
            sql = new_sql

        return sql