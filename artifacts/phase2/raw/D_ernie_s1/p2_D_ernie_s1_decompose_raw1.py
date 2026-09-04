"""Decomposes a Text-to-SQL question into ordered sub-questions, answers each with a small LLM call, then assembles the final SQL."""
from ..harness_base import SQLHarness
from .. import bridge
import json

class P2P2DErnieS1Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the question into ordered sub-questions
        decompose_prompt = (
            f"Given the following database schema and question, break the question into a sequence of ordered, "
            f"simpler sub-questions that can each be answered with a single small SQL query. "
            f"Return a JSON array of strings, where each string is a sub-question. "
            f"Do not include any explanation, just the JSON array.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Sub-questions (JSON array):"
        )
        decompose_response = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        # Extract the JSON array from the response
        try:
            sub_questions = json.loads(bridge.extract_sql(decompose_response))
        except json.JSONDecodeError:
            # Fallback: try to find a JSON array in the text
            import re
            match = re.search(r'\[.*?\]', decompose_response, re.DOTALL)
            if match:
                sub_questions = json.loads(match.group())
            else:
                # If we can't parse, treat the whole response as a single sub-question
                sub_questions = [question]

        # Step 2: Answer each sub-question with a small LLM call
        results = []
        context = ""
        for i, sub_q in enumerate(sub_questions):
            # Build prompt for generating SQL for this sub-question
            if i == 0:
                sql_prompt = (
                    f"Given the following database schema and question, write a single SQL query to answer it. "
                    f"Return only the SQL query, nothing else.\n\n"
                    f"Schema:\n{self.schema}\n\n"
                    f"Question: {sub_q}\n\n"
                    f"SQL:"
                )
            else:
                # Include context from previous results
                sql_prompt = (
                    f"Given the following database schema, previous query results, and a new question, "
                    f"write a single SQL query to answer the new question. "
                    f"Return only the SQL query, nothing else.\n\n"
                    f"Schema:\n{self.schema}\n\n"
                    f"Previous results:\n{context}\n\n"
                    f"New question: {sub_q}\n\n"
                    f"SQL:"
                )
            sql_response = self.llm(sql_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_response)
            # Execute the SQL
            exec_result = self.execute(sql)
            if not exec_result["ok"]:
                # If execution fails, we might retry or use a fallback? For now, we'll use an empty result.
                rows_str = "Error: " + exec_result.get("error", "unknown")
            else:
                # Convert rows to a string representation for context
                rows_str = str(exec_result["rows"])
            results.append(rows_str)
            # Update context: include the current sub-question and its result
            context += f"Sub-question {i+1}: {sub_q}\nResult: {rows_str}\n\n"

        # Step 3: Assemble the final SQL using all intermediate results
        assemble_prompt = (
            f"Given the following database schema, the original question, and the results of intermediate sub-queries, "
            f"write a single SQL query that answers the original question by combining the intermediate results. "
            f"Return only the SQL query, nothing else.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Original question: {question}\n\n"
            f"Intermediate results:\n{context}\n\n"
            f"Final SQL:"
        )
        assemble_response = self.llm(assemble_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(assemble_response)
        return final_sql