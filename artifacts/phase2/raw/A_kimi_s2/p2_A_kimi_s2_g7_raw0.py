"""Two-stage Text-to-SQL: first generate a structured query plan, then generate SQL from the plan."""
# MECHANISM: twostage

from ..harness_base import SQLHarness
from .. import bridge
import json
import re


class P2P2AKimiS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: Generate a structured query plan as an intermediate artifact
        plan_system = (
            "You are a SQL query planning assistant. Your job is to analyze a database schema "
            "and a natural language question, then produce a structured query plan in JSON format. "
            "The plan must include these fields:\n"
            "- 'select': list of columns/expressions to select\n"
            "- 'from': list of tables\n"
            "- 'joins': list of join descriptions (e.g., 'tableA.id = tableB.fk_id')\n"
            "- 'where': list of filter conditions\n"
            "- 'aggregations': list of aggregation expressions (e.g., 'COUNT(*)')\n"
            "- 'group_by': list of columns\n"
            "- 'order_by': list of columns with optional ASC/DESC\n"
            "- 'limit': integer or null\n"
            "Output ONLY valid JSON, no markdown, no explanation."
        )

        plan_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Produce the query plan JSON."
        )

        plan_response = self.llm(plan_prompt, system=plan_system, temperature=0.0, n=1)

        # Parse the plan from the response
        plan = self._extract_json_plan(plan_response)

        # Stage 2: Generate SQL using the plan as a guide
        sql_system = (
            "You are a SQL generation assistant. Given a database schema, a question, and a "
            "structured query plan, write the correct SQL query. Follow the plan precisely. "
            "Output ONLY the SQL query, no markdown, no explanation."
        )

        sql_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Query Plan:\n{json.dumps(plan, indent=2)}\n\n"
            "Generate the SQL query."
        )

        sql_response = self.llm(sql_prompt, system=sql_system, temperature=0.0, n=1)

        final_sql = bridge.extract_sql(sql_response)
        return final_sql

    def _extract_json_plan(self, text: str) -> dict:
        """Extract a JSON plan from LLM output, with fallback."""
        # Strip markdown code blocks if present
        text = re.sub(r'^