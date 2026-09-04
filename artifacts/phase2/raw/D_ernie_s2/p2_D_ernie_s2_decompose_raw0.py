"""Decompose a complex Text-to-SQL question into ordered sub-questions, solve each with a small LLM call, then assemble the final SQL."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the main question into ordered sub-questions.
        decompose_prompt = (
            f"Given the following question and database schema, break it down into "
            f"ordered sub-questions that together answer the main question. "
            f"Output each sub-question on a new line, numbered starting from 1. "
            f"Question: {question}\nSchema: {self.schema}"
        )
        decompose_response = self.llm(
            decompose_prompt, system="", temperature=0.0, n=1
        )
        sub_questions = [
            line.strip()
            for line in decompose_response.split("\n")
            if line.strip() and line.strip()[0].isdigit()
        ]
        # Fallback: if parsing fails, treat the whole question as a single sub-question.
        if not sub_questions:
            sub_questions = [question]

        # Step 2: Generate a SQL query for each sub-question.
        sub_sqls = []
        for sq in sub_questions:
            sql_prompt = (
                f"Given the following question and database schema, write a SQL query "
                f"that answers the question. Use only the provided schema. "
                f"Question: {sq}\nSchema: {self.schema}"
            )
            sql_response = self.llm(
                sql_prompt, system="", temperature=0.0, n=1
            )
            extracted_sql = bridge.extract_sql(sql_response)
            if extracted_sql:
                sub_sqls.append(extracted_sql)
            else:
                # If extraction fails, keep the raw response (might be empty).
                sub_sqls.append(sql_response)

        # Step 3: Assemble the final SQL by combining the sub-queries.
        if len(sub_sqls) == 1:
            final_sql = sub_sqls[0]
        else:
            combine_prompt = (
                f"Given the following list of SQL queries that each answer a part of the "
                f"original question, combine them into a single SQL query that answers "
                f"the original question. Use only the provided schema. "
                f"Original question: {question}\nSQL parts: {sub_sqls}\nSchema: {self.schema}"
            )
            combine_response = self.llm(
                combine_prompt, system="", temperature=0.0, n=1
            )
            final_sql = bridge.extract_sql(combine_response)
            if not final_sql:
                # Fallback: if extraction fails, return the first sub-SQL (or empty).
                final_sql = sub_sqls[0] if sub_sqls else ""

        # Optional verification: execute the final SQL to ensure it runs (but not required).
        # Uncomment the following lines if verification is desired.
        # result = self.execute(final_sql)
        # if not result["ok"]:
        #     # If execution fails, try to fix by re-decomposing or returning empty.
        #     final_sql = ""

        return final_sql