"""Decomposes a complex Text-to-SQL question into ordered sub-questions, answers each with a small LLM call, then assembles the final SQL."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the question into ordered sub-questions
        decompose_prompt = f"Given the following question and database schema, break it down into a sequence of ordered sub-questions that can be answered step by step to build the final SQL. Output the sub-questions as a numbered list (one per line). Question: {question}\nSchema: {self.schema}"
        decompose_response = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        lines = decompose_response.strip().split('\n')
        sub_questions = []
        for line in lines:
            line = line.strip()
            if line:
                if '.' in line:
                    text = line.split('.', 1)[1].strip()
                else:
                    text = line
                sub_questions.append(text)
        
        if not sub_questions:
            sub_questions = [question]
        
        # Step 2: Answer each sub-question with a small LLM call to get partial SQL
        partial_sqls = []
        for sub_q in sub_questions:
            prompt = f"Given the database schema and the following sub-question (which is part of a larger question), write the SQL query to answer it. Schema: {self.schema}\nSub-question: {sub_q}"
            sql_response = self.llm(prompt, system="", temperature=0.0, n=1)
            partial_sql = bridge.extract_sql(sql_response)
            partial_sqls.append(partial_sql)
        
        # Step 3: Assemble the final SQL from the partial SQLs and the original question
        assemble_prompt = f"Given the original question and the following partial SQL queries that answer parts of the question, write the final SQL query that answers the original question by combining these partial queries appropriately. Original question: {question}\nPartial SQLs: {partial_sqls}"
        final_sql_response = self.llm(assemble_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(final_sql_response)
        
        return final_sql