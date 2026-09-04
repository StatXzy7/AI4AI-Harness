"""This harness decomposes a Text-to-SQL question into ordered sub-questions, generates a SQL CTE for each, and assembles a final SQL query from those CTEs."""
import json
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS0Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        llm = self.llm

        # Step 1: Decompose the question into ordered sub-questions
        decomposition_prompt = f"""You are an expert Text-to-SQL planner.

Database schema:
{schema}

Question: {question}

Break the question into ordered sub-questions that can each be answered by a SQL query.
Output a JSON array of strings, e.g. ["First sub-question", "Second sub-question"].
Ensure sub-questions are ordered logically and cover all parts of the original question. Keep it minimal."""
        decomp_text = self._call_llm(llm, decomposition_prompt)
        subquestions = self._parse_list(decomp_text)

        if not subquestions:
            # Fallback: direct single-shot SQL generation
            return self._direct_sql(question)

        # Step 2: Generate a SQL CTE for each sub-question in order
        ctes = []
        for i, subq in enumerate(subquestions):
            name = f"subq{i}"
            cte_context = self._format_cte_context(ctes)

            sql_prompt = f"""You are an expert SQL engineer.

Database schema:
{schema}

Original question: {question}
Sub-question to answer now: {subq}

Existing CTEs (use them if helpful):
{cte_context if cte_context else "(none)"}

Write a single SELECT statement that answers the sub-question. It may reference the existing CTEs by name.
Output only the SQL, no explanation."""
            sql_text = self._call_llm(llm, sql_prompt)
            extracted = bridge.extract_sql(sql_text) or sql_text.strip()
            extracted = self._clean_sql(extracted)
            if extracted:
                ctes.append((name, extracted))

        # Step 3: Assemble the final SQL using the generated CTEs
        final_sql = self._assemble_sql(question, ctes)
        return final_sql

    def _call_llm(self, llm, prompt: str) -> str:
        """Call the LLM and normalize the response to a string."""
        res = llm(prompt, system="", temperature=0.0, n=1)
        if isinstance(res, (list, tuple)):
            return str(res[0]) if res else ""
        if isinstance(res, dict):
            for key in ("text", "content", "message", "response", "completion"):
                if key in res:
                    return str(res[key])
        return str(res)

    def _clean_sql(self, sql: str) -> str:
        """Remove code fences, trailing semicolons, and extra whitespace."""
        sql = sql.strip()
        # Remove markdown code fences if present
        sql = re.sub(r'^