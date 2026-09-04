"""Two-stage Text-to-SQL harness where an LLM first proposes a structured plan and a second LLM call generates SQL conditioned on that plan."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


PLAN_SYSTEM = (
    "You are a database analysis expert. Given a natural language question and a SQL "
    "schema, produce a concise step-by-step plan for writing the SQL query. "
    "The plan should identify relevant tables, columns, join conditions, filters, "
    "grouping, ordering, and limits. Do NOT write SQL. Output only the plan."
)

SQL_SYSTEM = (
    "You are an expert SQL writer. Given a natural language question, the database "
    "schema, and a written plan, produce a single executable SQL query that answers "
    "the question. Output only the SQL query with no commentary."
)


class P2P2AMinimaxS2G7(SQLHarness):
    def _plan_prompt(self, question: str) -> str:
        return (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a concise plan for the SQL query."
        )

    def _sql_prompt(self, question: str, plan: str) -> str:
        return (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan}\n\n"
            "Write the SQL query that implements this plan."
        )

    def _truncate(self, text: str, limit: int = 4000) -> str:
        if text is None:
            return ""
        if len(text) <= limit:
            return text
        return text[:limit] + "\n... [truncated]"

    def solve(self, question: str) -> str:
        # Stage 1: produce a plan from the schema + question.
        plan_text = self.llm(
            self._plan_prompt(question),
            system=PLAN_SYSTEM,
            temperature=0.0,
            n=1,
        )
        plan_text = self._truncate(plan_text, 2000)

        # Stage 2: produce SQL conditioned on the plan.
        raw_sql = self.llm(
            self._sql_prompt(question, plan_text),
            system=SQL_SYSTEM,
            temperature=0.0,
            n=1,
        )

        sql = bridge.extract_sql(raw_sql)
        if not sql:
            # Fallback: try to use the raw text if extraction fails.
            sql = raw_sql.strip()

        return sql