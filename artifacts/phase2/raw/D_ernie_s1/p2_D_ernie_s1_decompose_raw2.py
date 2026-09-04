"""Decomposes the question into ordered sub-questions, generates a SQL query for each via LLM, then assembles a final SQL query via LLM."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS1Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the original question into a list of ordered sub-questions
        decompose_prompt = (
            f"Given the following question and database schema, break it down into a sequence of "
            f"simpler sub-questions that can be answered with SQL. Output each sub-question on a new "
            f"line, numbered starting from 1.\n\n"
            f"Question: {question}\n\n"
            f"Schema: {self.schema}\n\n"
            f"Sub-questions:"
        )
        decompose_response = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        lines = decompose_response.strip().split('\n')
        sub_questions = []
        for line in lines:
            line = line.strip()
            if line:
                # Remove leading number and dot if present (e.g., "1. What is ...")
                if line[0].isdigit() and '.' in line:
                    line = line.split('.', 1)[1].strip()
                sub_questions.append(line)
        if not sub_questions:
            sub_questions = [question]  # fallback to original question

        # Step 2: Generate a SQL query for each sub-question using the LLM
        sub_queries = []
        for sq in sub_questions:
            prompt = (
                f"Given the following sub-question and database schema, write a SQL query that "
                f"answers it. Only output the SQL query, nothing else.\n\n"
                f"Sub-question: {sq}\n\n"
                f"Schema: {self.schema}\n\n"
                f"SQL:"
            )
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            if sql:
                sub_queries.append(sql)
            else:
                # If extraction fails, use the raw response as a fallback (may be invalid)
                sub_queries.append(response)

        # Step 3: Assemble the final SQL query from the sub-queries via LLM
        sub_queries_text = "\n".join(
            f"Sub-query {i+1}: {sq}" for i, sq in enumerate(sub_queries)
        )
        assemble_prompt = (
            f"Given the original question, database schema, and a set of sub-queries that answer "
            f"parts of the question, combine them into a single SQL query that answers the original "
            f"question. Only output the final SQL query.\n\n"
            f"Original question: {question}\n\n"
            f"Schema: {self.schema}\n\n"
            f"Sub-queries:\n{sub_queries_text}\n\n"
            f"Final SQL:"
        )
        final_response = self.llm(assemble_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(final_response)
        if not final_sql:
            # Fallback: use the raw response as the final SQL
            final_sql = final_response
        return final_sql