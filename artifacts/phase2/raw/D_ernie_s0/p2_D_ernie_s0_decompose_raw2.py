"""Decomposes a Text-to-SQL question into ordered sub-questions, solves each with a small LLM call, and assembles the final SQL from intermediate results."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS0Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the main question into ordered sub-questions
        decompose_prompt = (
            f"Break the following question into a list of ordered sub-questions that can be answered "
            f"with SQL queries. Each sub-question should be simple and answerable independently. "
            f"Only output the sub-questions, one per line, in order.\n\nQuestion: {question}"
        )
        decompose_response = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        sub_questions = [
            line.strip() for line in decompose_response.strip().split('\n') 
            if line.strip()
        ]
        
        # Step 2: Solve each sub-question with a small LLM call
        sub_sqls = []
        sub_results = []
        
        for i, sub_q in enumerate(sub_questions):
            sub_prompt = (
                f"Given the following database schema and sub-question, write a SQL query to answer it. "
                f"Only output the SQL query.\n\nSchema: {self.schema}\n\nSub-question: {sub_q}"
            )
            sub_response = self.llm(sub_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sub_response)
            
            # Execute the sub-query to get results
            exec_result = self.execute(sql)
            if exec_result["ok"]:
                sub_sqls.append(sql)
                sub_results.append(exec_result["rows"])
            else:
                # If execution fails, use empty result and continue
                sub_sqls.append(sql)
                sub_results.append([])
        
        # Step 3: Assemble the final SQL from intermediate results
        assembly_prompt = (
            f"Using the results of the following sub-queries, write a SQL query that answers the original question. "
            f"Only output the final SQL query.\n\nOriginal question: {question}\n\n"
            f"Sub-queries and their results:\n" +
            "\n".join(
                f"Sub-query {i+1}: {sql}\nResult: {result}" 
                for i, (sql, result) in enumerate(zip(sub_sqls, sub_results))
            )
        )
        assembly_response = self.llm(assembly_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(assembly_response)
        
        return final_sql