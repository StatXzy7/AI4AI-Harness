"""This harness decomposes a Text-to-SQL question into ordered sub-questions, answers each with a small LLM call, and assembles the final SQL query."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS2Decompose(SQLHarness):
    """Decomposes a complex Text-to-SQL question into ordered sub-questions, answers each with a small LLM call to generate SQL, and assembles the final query by combining the sub-queries via another LLM call."""

    def solve(self, question: str) -> str:
        # Step 1: Decompose the question into a list of ordered sub-questions
        decompose_prompt = f"""Break the following question into a sequence of simpler sub-questions that, when answered in order, can be used to construct the final SQL query. Output as a numbered list, each on a new line, with format: '1. sub-question' etc.

Question: {question}

Decomposition:"""
        decompose_response = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        lines = decompose_response.strip().split('\n')
        sub_questions = []
        for line in lines:
            line = line.strip()
            if line and line[0].isdigit() and '.' in line:
                sub_q = line.split('.', 1)[1].strip()
                if sub_q:
                    sub_questions.append(sub_q)
        if not sub_questions:
            sub_questions = [question]

        # Step 2: Answer each sub-question with a small LLM call to generate a SQL fragment
        sub_sqls = []
        for sub_q in sub_questions:
            sql_prompt = f"""Given the schema:
{self.schema}

And the sub-question: '{sub_q}'

Generate a SQL query that answers this sub-question. Output only the SQL query."""
            sql_response = self.llm(sql_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_response)
            sub_sqls.append(sql)

        # Step 3: Assemble the final SQL by combining the sub-queries via another LLM call
        context = ""
        for sub_q, sql in zip(sub_questions, sub_sqls):
            context += f"Sub-question: {sub_q}\nSQL: {sql}\n\n"
        assemble_prompt = f"""Given the original question: '{question}'
And the following sub-questions and their SQL queries:
{context}
Generate a single SQL query that answers the original question by combining these sub-queries appropriately. Output only the SQL query."""
        assemble_response = self.llm(assemble_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(assemble_response)
        return final_sql