"""Decomposes a Text-to-SQL question into ordered sub-questions, answers each with a small LLM call, then assembles the final SQL."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the original question into ordered sub-questions
        decompose_prompt = (
            f"Given the following question and the database schema, break it into a sequence of "
            f"simpler, ordered sub-questions that, when answered in order, will help answer the "
            f"original question. Output the sub-questions as a numbered list, one per line.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}"
        )
        decomposition_text = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        # Parse sub-questions: assume each line starting with a number is a sub-question
        sub_questions = []
        for line in decomposition_text.strip().split('\n'):
            line = line.strip()
            if line and line[0].isdigit():
                # Remove the leading number and period
                sub_q = line.split('.', 1)[1].strip()
                if sub_q:
                    sub_questions.append(sub_q)
        if not sub_questions:
            # Fallback: treat the whole question as a single sub-question
            sub_questions = [question]

        # Step 2: Answer each sub-question with a small LLM call to generate SQL
        intermediate_sqls = []
        for i, sub_q in enumerate(sub_questions):
            sub_prompt = (
                f"Given the database schema and the following sub-question, write a SQL query that "
                f"answers it. Output only the SQL query.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Sub-question: {sub_q}"
            )
            sql_text = self.llm(sub_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_text)
            if sql:
                intermediate_sqls.append(sql)
            else:
                # If extraction fails, use a placeholder (should not happen in practice)
                intermediate_sqls.append("SELECT 1")

        # Step 3: Assemble the final SQL from the intermediate queries
        assemble_prompt = (
            f"Given the original question, the database schema, and the following intermediate SQL "
            f"queries (each answering a sub-question in order), write a single SQL query that "
            f"answers the original question. Output only the SQL query.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Original question: {question}\n\n"
            f"Intermediate SQLs:\n" + "\n".join(
                f"{i+1}. {sql}" for i, sql in enumerate(intermediate_sqls)
            )
        )
        final_sql_text = self.llm(assemble_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(final_sql_text)

        # Return the extracted SQL (or a fallback if extraction fails)
        return final_sql if final_sql else "SELECT 1"