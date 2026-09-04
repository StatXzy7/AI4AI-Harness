"""Decomposes a Text-to-SQL question into ordered sub-questions, answers each with a small LLM call, and assembles the final SQL."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS0Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the question into ordered sub-questions
        decompose_prompt = f"""Given the following database schema and question, break the question into an ordered list of sub-questions that, when answered in order, will help in constructing the final SQL query.

Schema: {self.schema}

Question: {question}

Please output the sub-questions as a numbered list, one per line."""
        decomp_response = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        # Parse sub-questions: split by newline, keep lines starting with a digit
        sub_questions = []
        for line in decomp_response.split('\n'):
            line = line.strip()
            if line and line[0].isdigit():
                # Remove the leading number and period
                sub_q = line.split('.', 1)[1].strip() if '.' in line else line
                if sub_q:
                    sub_questions.append(sub_q)
        
        if not sub_questions:
            # Fallback: treat the whole question as a single sub-question
            sub_questions = [question]
        
        # Step 2: Answer each sub-question with a small LLM call to get intermediate SQL
        intermediate_sqls = []
        for sq in sub_questions:
            sub_prompt = f"""Given the database schema and the following sub-question, write a SQL query that answers the sub-question.

Schema: {self.schema}

Sub-question: {sq}

Please output only the SQL query."""
            sub_response = self.llm(sub_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sub_response)
            if sql:
                intermediate_sqls.append(sql)
        
        # Step 3: Assemble the final SQL from intermediate results
        if not intermediate_sqls:
            # If no intermediate SQLs, attempt direct generation
            assemble_prompt = f"""Given the database schema and the following question, write the SQL query that answers the question.

Schema: {self.schema}

Question: {question}

Please output only the SQL query."""
            final_response = self.llm(assemble_prompt, system="", temperature=0.0, n=1)
            return bridge.extract_sql(final_response)
        
        assemble_prompt = f"""Given the database schema, the original question, and the following intermediate SQL queries, write the final SQL query that answers the original question.

Schema: {self.schema}

Original question: {question}

Intermediate SQLs:
{chr(10).join(intermediate_sqls)}

Please output only the final SQL query."""
        final_response = self.llm(assemble_prompt, system="", temperature=0.0, n=1)
        return bridge.extract_sql(final_response)