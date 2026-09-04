"""Decomposes a Text-to-SQL question into ordered sub-questions, answers each with a small LLM call, and assembles the final SQL from the fragments."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS0Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the main question into ordered sub-questions
        decompose_prompt = f"""Given the following question and database schema, break the question into ordered sub-questions that each ask for a specific part of the SQL query. The parts are: SELECT, FROM, WHERE, GROUP BY, HAVING, ORDER BY. Output each sub-question on a new line in the format: 'Q{{i}}: [{{PART}}] {{sub-question}}' where {{i}} is the index, {{PART}} is one of the parts, and {{sub-question}} is the question for that part. Only include the parts that are needed.

Question: {question}

Schema: {self.schema}"""
        decompose_response = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        # Parse the sub-questions: split by newline, filter non-empty, extract part and sub-question
        lines = [line.strip() for line in decompose_response.split('\n') if line.strip()]
        parts = []
        for line in lines:
            # Expected format: "Q1: [SELECT] ..."
            if ': [' in line:
                # Split at the first ': [' to get index and rest
                idx_part, rest = line.split(': [', 1)
                # Extract part (until ']')
                part_end = rest.find(']')
                if part_end != -1:
                    part = rest[:part_end]
                    sub_q = rest[part_end+1:].strip()
                    parts.append((part, sub_q))
        # If no parts found, fallback to direct generation
        if not parts:
            direct_prompt = f"Given the question and schema, generate the SQL query directly.\n\nQuestion: {question}\n\nSchema: {self.schema}"
            direct_sql = self.llm(direct_prompt, system="", temperature=0.0, n=1)
            return bridge.extract_sql(direct_sql)

        # Step 2: Generate SQL fragment for each part in order
        fragments = []
        for part, sub_q in parts:
            if part == "SELECT":
                prompt = f"Given the question and schema, generate only the SELECT clause for the query. Do not include FROM, WHERE, etc. Output only the SELECT clause (e.g., 'SELECT column1, column2').\n\nQuestion: {sub_q}\n\nSchema: {self.schema}"
            elif part == "FROM":
                prompt = f"Given the question and schema, generate only the FROM clause for the query. Do not include SELECT, WHERE, etc. Output only the FROM clause (e.g., 'FROM table1, table2').\n\nQuestion: {sub_q}\n\nSchema: {self.schema}"
            elif part == "WHERE":
                prompt = f"Given the question and schema, generate only the WHERE clause for the query. Do not include SELECT, FROM, etc. Output only the WHERE clause (e.g., 'WHERE condition').\n\nQuestion: {sub_q}\n\nSchema: {self.schema}"
            elif part == "GROUP BY":
                prompt = f"Given the question and schema, generate only the GROUP BY clause for the query. Do not include SELECT, FROM, WHERE, etc. Output only the GROUP BY clause (e.g., 'GROUP BY column1').\n\nQuestion: {sub_q}\n\nSchema: {self.schema}"
            elif part == "HAVING":
                prompt = f"Given the question and schema, generate only the HAVING clause for the query. Do not include SELECT, FROM, WHERE, GROUP BY, etc. Output only the HAVING clause (e.g., 'HAVING condition').\n\nQuestion: {sub_q}\n\nSchema: {self.schema}"
            elif part == "ORDER BY":
                prompt = f"Given the question and schema, generate only the ORDER BY clause for the query. Do not include SELECT, FROM, WHERE, GROUP BY, HAVING, etc. Output only the ORDER BY clause (e.g., 'ORDER BY column1 DESC').\n\nQuestion: {sub_q}\n\nSchema: {self.schema}"
            else:
                # Unknown part, skip or generate entire query? We'll skip and hope it doesn't happen.
                continue
            fragment_text = self.llm(prompt, system="", temperature=0.0, n=1)
            fragment = bridge.extract_sql(fragment_text)
            if fragment:
                fragments.append(fragment)

        # Step 3: Assemble the final SQL by concatenating fragments in order
        if fragments:
            final_sql = " ".join(fragments)
            # Ensure the SQL is syntactically valid by extracting again (in case of concatenation issues)
            final_sql = bridge.extract_sql(final_sql)
            return final_sql
        else:
            # Fallback if no fragments generated
            direct_prompt = f"Given the question and schema, generate the SQL query directly.\n\nQuestion: {question}\n\nSchema: {self.schema}"
            direct_sql = self.llm(direct_prompt, system="", temperature=0.0, n=1)
            return bridge.extract_sql(direct_sql)