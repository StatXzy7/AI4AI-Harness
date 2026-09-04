"""Break a Text-to-SQL question into ordered sub-questions, answer each with a small LLM call, then assemble those answers into a final SQL query."""
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        sub_questions = self._decompose_question(question)
        previous_answers = []
        for sub_q in sub_questions:
            answer = self._answer_subquestion(question, sub_q, previous_answers)
            previous_answers.append((sub_q, answer))
        final_sql = self._assemble_sql(question, previous_answers)
        return final_sql

    def _call_llm(self, prompt: str, system: str = "") -> str:
        result = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(result, list):
            result = result[0] if result else ""
        if isinstance(result, dict):
            result = result.get("text") or result.get("content") or ""
        return str(result)

    def _decompose_question(self, question: str) -> list[str]:
        prompt = f"""You are an expert at breaking complex Text-to-SQL questions into ordered, simple sub-questions.
Given the database schema and the original question, produce a numbered list of concise sub-questions.
The sub-questions should be ordered so that later ones may depend on earlier answers.
Return ONLY the numbered list, one sub-question per line, without any additional commentary.

Database schema:
{self.schema}

Original question:
{question}

Example output:
1. Find the customer id of ...
2. For each such customer, calculate ...
"""
        raw = self._call_llm(prompt)
        items = self._parse_numbered_list(raw)
        if not items:
            items = [question]
        return items

    def _parse_numbered_list(self, text: str) -> list[str]:
        items = []
        for line in text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r'^\s*(?:\d+[\.\):\-]|\-|\*)\s*(.+)$', line)
            if m:
                items.append(m.group(1).strip())
            elif line.lower().startswith(('first', 'second', 'third', 'finally', 'next', 'then')):
                items.append(line)
        return items

    def _answer_subquestion(self, question: str, sub_q: str, previous_answers: list[tuple[str, str]]) -> str:
        prev_lines = []
        for i, (q, a) in enumerate(previous_answers, 1):
            prev_lines.append(f"{i}. Sub-question: {q}\n   Answer: {a}")
        prev_text = "\n".join(prev_lines) if prev_lines else "(none)"
        prompt = f"""You are an expert Text-to-SQL reasoning assistant.
Use the database schema and, if provided, previous sub-question answers to answer the current sub-question.
Provide a concise factual answer that will later help write a SQL query.

Database schema:
{self.schema}

Original question:
{question}

Previous sub-answers:
{prev_text}

Current sub-question:
{sub_q}

Answer:
"""
        return self._call_llm(prompt).strip()

    def _assemble_sql(self, question: str, sub_answers: list[tuple[str, str]]) -> str:
        entries = []
        for i, (q, a) in enumerate(sub_answers, 1):
            entries.append(f"{i}. Sub-question: {q}\n   Answer: {a}")
        decomp_text = "\n".join(entries)
        prompt = f"""You are an expert SQL query writer.
Given a database schema, an original question, and an ordered decomposition with answers, write a single SQLite SQL query that correctly answers the original question.
Use the answers to the sub-questions as facts for the query.

Database schema:
{self.schema}

Original question:
{question}

Decomposition with answers:
{decomp_text}

Return only the SQL query, without any explanation or markdown formatting.
"""
        raw = self._call_llm(prompt)
        sql = bridge.extract_sql(raw)
        if sql:
            return sql.strip()
        return raw.strip()