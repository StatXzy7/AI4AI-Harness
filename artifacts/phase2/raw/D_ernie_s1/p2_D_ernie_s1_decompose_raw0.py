"""Decompose question into ordered sub-questions, generate SQL for each via LLM, then assemble final SQL."""

import json
from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS1Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the question into ordered sub-questions.
        decompose_prompt = f"""Given the following question and database schema, break it down into a sequence of simpler sub-questions that, when answered in order, would help answer the original question. Output a JSON array of strings, each being a sub-question.

Question: {question}

Schema: {self.schema}

Sub-questions:"""
        decompose_response = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        # Extract the JSON array from the response.
        try:
            start = decompose_response.find('[')
            end = decompose_response.rfind(']') + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON array found.")
            json_str = decompose_response[start:end]
            sub_questions = json.loads(json_str)
        except Exception:
            # Fallback: use the original question as the only sub-question.
            sub_questions = [question]

        # Step 2: For each sub-question, generate a SQL query.
        sub_queries = []
        for sq in sub_questions:
            sub_prompt = f"""Given the following sub-question and database schema, write a SQL query that answers it. Output only the SQL query.

Sub-question: {sq}

Schema: {self.schema}

SQL:"""
            sub_sql_response = self.llm(sub_prompt, system="", temperature=0.0, n=1)
            sql_fragment = bridge.extract_sql(sub_sql_response)
            sub_queries.append(sql_fragment)

        # Step 3: Assemble the final SQL from the sub-queries.
        assemble_prompt = f"""Given the following sub-queries (each answering a part of the original question) and the original question, write a single SQL query that answers the original question by combining these sub-queries appropriately (using subqueries, CTEs, joins, etc.). Output only the final SQL query.

Original question: {question}

Sub-queries:
{chr(10).join(sub_queries)}

Schema: {self.schema}

Final SQL:"""
        final_sql_response = self.llm(assemble_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(final_sql_response)

        return final_sql