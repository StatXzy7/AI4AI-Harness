"""Decompose the question into ordered sub-questions, generate a SQL snippet for each via LLM calls, then assemble the final SQL."""

from ..harness_base import SQLHarness
from .. import bridge
import json


class P2P2DErnieS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the question into ordered sub-questions using LLM
        decompose_prompt = f"""Given the following question and database schema, break the question into a series of ordered sub-questions that are easier to answer. Each sub-question should be a simple question that can be answered with a small SQL query. Return the sub-questions as a JSON array of strings.

Question: {question}
Schema: {self.schema}

Sub-questions:"""
        decompose_response = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        sub_questions_text = bridge.extract_sql(decompose_response)
        
        try:
            sub_questions = json.loads(sub_questions_text)
        except json.JSONDecodeError:
            # Fallback: treat the entire question as a single sub-question if parsing fails
            sub_questions = [question]

        # Step 2: Generate a SQL snippet for each sub-question using LLM
        sql_snippets = []
        for i, sub_q in enumerate(sub_questions):
            prompt = f"""Given the following sub-question and the database schema, write a SQL query that answers the sub-question. The query should return a result set that can be used in a larger query (for example, as a CTE). Use the table and column names from the schema.

Sub-question: {sub_q}
Schema: {self.schema}

SQL Query:"""
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql_snippet = bridge.extract_sql(response)
            sql_snippets.append(sql_snippet)

        # Step 3: Assemble the final SQL by combining the snippets using LLM
        sub_q_snippet_pairs = "\n".join([
            f"Sub-question {i+1}: {sq}\nSQL: {snip}"
            for i, (sq, snip) in enumerate(zip(sub_questions, sql_snippets))
        ])
        assemble_prompt = f"""Given the original question, the database schema, and the following SQL queries for each sub-question, combine them into a single SQL query that answers the original question.

Original Question: {question}
Schema: {self.schema}

Sub-questions and their SQL:
{sub_q_snippet_pairs}

Final SQL Query:"""
        final_response = self.llm(assemble_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(final_response)

        return final_sql