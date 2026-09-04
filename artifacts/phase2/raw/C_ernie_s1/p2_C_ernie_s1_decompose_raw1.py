"""Decomposes Text-to-SQL questions into ordered sub-questions, solves each with LLM calls, then assembles the final SQL."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS1Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the main question into ordered sub-questions
        decompose_prompt = f"""Given the following database schema and question, break it into 3-5 ordered sub-questions that can each be answered with a simple SQL query. Return only the sub-questions, one per line, numbered 1, 2, 3, etc.

Schema: {self.schema}

Question: {question}

Sub-questions:"""
        
        sub_questions_text = self.llm(
            decompose_prompt, 
            system="", 
            temperature=0.0, 
            n=1
        )
        
        # Parse sub-questions from the response
        sub_questions = []
        for line in sub_questions_text.strip().split('\n'):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith('-') or line.startswith('*')):
                # Remove numbering/bullets if present
                if line[0].isdigit():
                    line = line.split('.', 1)[1] if '.' in line else line
                elif line.startswith('-') or line.startswith('*'):
                    line = line[1:].strip()
                sub_questions.append(line.strip())
        
        if not sub_questions:
            # Fallback: treat original question as single sub-question
            sub_questions = [question]
        
        # Step 2: Solve each sub-question with a small LLM call
        sub_queries = []
        for i, sub_q in enumerate(sub_questions):
            solve_prompt = f"""Given the following database schema and sub-question, write a SQL query that answers it. Return only the SQL query.

Schema: {self.schema}

Sub-question {i+1}: {sub_q}

SQL:"""
            
            sql_text = self.llm(
                solve_prompt, 
                system="", 
                temperature=0.0, 
                n=1
            )
            
            sql = bridge.extract_sql(sql_text)
            sub_queries.append(sql)
        
        # Step 3: Assemble the final SQL from sub-queries
        # Use the last sub-query as base and incorporate previous ones via CTEs
        if len(sub_queries) == 1:
            final_sql = sub_queries[0]
        else:
            # Build CTEs from all but the last sub-query
            ctes = []
            for i, sql in enumerate(sub_queries[:-1]):
                cte_name = f"subq{i+1}"
                ctes.append(f"{cte_name} AS ({sql})")
            
            # The last sub-query becomes the main query, referencing CTEs if needed
            last_query = sub_queries[-1]
            
            # Simple assembly: wrap earlier queries as CTEs and use last as main
            assemble_prompt = f"""Given the following database schema and a set of sub-queries that answer parts of a question, combine them into a single SQL query that answers the original question. Use CTEs for intermediate results. Return only the final SQL.

Schema: {self.schema}

Original question: {question}

Sub-queries (in order):
{chr(10).join(sub_queries)}

Final SQL:"""
            
            final_sql_text = self.llm(
                assemble_prompt, 
                system="", 
                temperature=0.0, 
                n=1
            )
            
            final_sql = bridge.extract_sql(final_sql_text)
        
        # Optional: Validate the final SQL by executing it
        # (Not required by the problem but good practice)
        # result = self.execute(final_sql)
        # if not result.get("ok"):
        #     # If execution fails, return the last sub-query as fallback
        #     final_sql = sub_queries[-1]
        
        return final_sql