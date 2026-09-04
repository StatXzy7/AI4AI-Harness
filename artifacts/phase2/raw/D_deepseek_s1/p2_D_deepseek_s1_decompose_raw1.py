"""Decompose question into ordered sub-questions, solve each with LLM, and assemble final SQL."""
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2DDeepseekS1Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        # Step 1: Decompose the question into ordered sub-questions
        decomp_prompt = f"""Given the database schema:
{schema}

Question: {question}

Break the question into ordered sub-questions that can be answered sequentially to help solve the original question. Output each sub-question on a new line, numbered. Do not include any other text."""
        decomp_output = self.llm(
            decomp_prompt,
            system="You are a helpful assistant that decomposes complex SQL questions into ordered sub-questions.",
            temperature=0.0,
            n=1
        )
        sub_questions = self._parse_sub_questions(decomp_output)
        if not sub_questions:
            # Fallback: treat original question as single sub-question
            sub_questions = [question]

        # Step 2: Generate SQL for each sub-question, maintaining CTEs
        ctes = []
        for idx, sub_q in enumerate(sub_questions, 1):
            previous_ctes = "\n".join(ctes) if ctes else "None"
            sub_prompt = f"""Schema:
{schema}

Previous CTEs (available for use):
{previous_ctes}

Sub-question {idx}: {sub_q}

Write a SQL SELECT statement that answers this sub-question. You may use the previous CTEs. Output only the SQL SELECT statement, no explanation."""
            sub_output = self.llm(
                sub_prompt,
                system="You are a SQL expert. Generate a SQL SELECT statement for the given sub-question.",
                temperature=0.0,
                n=1
            )
            sub_sql = bridge.extract_sql(sub_output)
            if sub_sql:
                # Remove trailing semicolon and extra whitespace
                sub_sql = sub_sql.strip().rstrip(';').strip()
                if sub_sql:
                    ctes.append(f"subq_{idx} AS (\n{sub_sql}\n)")

        # Step 3: Assemble final SQL from the CTEs
        if not ctes:
            # No sub-queries generated; fallback to a direct call
            final_prompt = f"""Schema:
{schema}

Question: {question}

Write the SQL query that answers the question. Output only SQL."""
            final_output = self.llm(
                final_prompt,
                system="You are a SQL expert. Write a SQL query to answer the question.",
                temperature=0.0,
                n=1
            )
            return bridge.extract_sql(final_output)

        cte_block = ",\n".join(ctes)
        assembly_prompt = f"""Schema:
{schema}

Original question: {question}

You have the following CTEs derived from sub-questions:
{cte_block}

Write the final SQL query that answers the original question, using these CTEs as needed. Output only SQL."""
        final_output = self.llm(
            assembly_prompt,
            system="You are a SQL expert. Assemble the final SQL query using the provided CTEs.",
            temperature=0.0,
            n=1
        )
        final_sql = bridge.extract_sql(final_output)
        return final_sql

    @staticmethod
    def _parse_sub_questions(text: str) -> list:
        """Parse numbered sub-questions from LLM output."""
        lines = text.strip().splitlines()
        sub_questions = []
        pattern = re.compile(r'^\s*\d+[.)]?\s*(.*)$')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            m = pattern.match(line)
            if m:
                sub_q = m.group(1).strip()
                if sub_q:
                    sub_questions.append(sub_q)
            else:
                # If the line doesn't start with a number, treat it as a sub-question
                sub_questions.append(line)
        return sub_questions