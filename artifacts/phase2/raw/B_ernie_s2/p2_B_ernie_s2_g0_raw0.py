"""Uses repair mechanism by executing generated SQL and feeding errors back for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BErnieS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Generate SQL for the given question using a repair loop: if execution fails,
        feed the error back to the LLM to produce a corrected query.
        """
        max_attempts = 3
        prompt_template = (
            "Given the schema:\n{schema}\n\n"
            "Question: {question}\n\n"
            "Generate a valid SQL query that answers the question. "
            "Do not include any explanation, only the SQL query."
        )

        # Initial generation
        prompt = prompt_template.format(schema=self.schema, question=question)
        raw_sql = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw_sql)

        for attempt in range(max_attempts):
            result = self.execute(sql)
            if result.get("ok", False):
                return sql

            # If not ok, prepare repair prompt
            error_msg = result.get("error", "Unknown error")
            repair_prompt = (
                "The following SQL query failed with error: {error}\n\n"
                "Schema: {schema}\n\n"
                "Question: {question}\n\n"
                "Generate a corrected SQL query that avoids the error. "
                "Do not include any explanation, only the SQL query."
            ).format(error=error_msg, schema=self.schema, question=question)
            raw_sql = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(raw_sql)

        # If all attempts fail, return the last generated SQL (best effort)
        return sql