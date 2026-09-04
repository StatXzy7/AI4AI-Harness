"""Decomposes a Text-to-SQL question into ordered sub-questions, answers each with a small LLM call, and assembles the final SQL."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the question into ordered sub-questions
        decompose_prompt = f"""Given the following question and database schema, break it down into a sequence of simpler sub-questions. Output each sub-question on a new line, numbered.

Schema:
{self.schema}

Question: {question}

Sub-questions:"""
        decomp_text = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        # Parse sub-questions: split by newline and extract lines that look like sub-questions
        sub_questions = []
        for line in decomp_text.strip().split('\n'):
            line = line.strip()
            if line:
                # Remove common prefixes like "1.", "Sub-question 1:", etc.
                if line[0].isdigit() and '.' in line:
                    line = line.split('.', 1)[1].strip()
                elif 'Sub-question' in line:
                    if ':' in line:
                        line = line.split(':', 1)[1].strip()
                sub_questions.append(line)
        # If no sub-questions parsed, treat the whole question as one sub-question
        if not sub_questions:
            sub_questions = [question]

        # Step 2: Answer each sub-question with a small SQL query
        sub_sqls = []
        for i, sq in enumerate(sub_questions):
            sub_prompt = f"""Given the schema and the following sub-question, write a SQL query that answers it. Only output the SQL query.

Schema:
{self.schema}

Sub-question: {sq}

SQL:"""
            sub_sql_text = self.llm(sub_prompt, system="", temperature=0.0, n=1)
            sql_snippet = bridge.extract_sql(sub_sql_text)
            sub_sqls.append(sql_snippet)

        # Step 3: Assemble the final SQL from the snippets
        combine_prompt = f"""Given the schema and the following SQL snippets that answer parts of the original question, combine them into a single SQL query that answers the original question. You may use subqueries, joins, or CTEs as needed. Only output the final SQL query.

Schema:
{self.schema}

Original question: {question}

SQL snippets:
{chr(10).join(f'Snippet {i+1}: {sql}' for i, sql in enumerate(sub_sqls))}

Final SQL:"""
        final_sql_text = self.llm(combine_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(final_sql_text)
        return final_sql