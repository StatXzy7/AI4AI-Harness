"""Break a natural-language question into ordered sub-questions, generate SQL for each with small LLM calls, and assemble the final SQL."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS0Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        sub_questions = self._decompose(question)
        if not sub_questions:
            return self._direct_sql(question)

        sub_queries = []
        for sub_q in sub_questions:
            sql = self._generate_sub_sql(sub_q)
            if sql:
                sub_queries.append((sub_q, sql))

        if not sub_queries:
            return self._direct_sql(question)

        final_sql = self._assemble_final_sql(question, sub_queries)
        if final_sql:
            return final_sql

        return self._direct_sql(question)

    def _decompose(self, question: str):
        prompt = (
            "You are given a database schema and a complex question. "
            "Break the question into a list of ordered, simpler sub-questions. "
            "Each sub-question should be answerable by a single SQL query over the schema.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only the ordered sub-questions, one per line. Do not include numbering or SQL."
        )
        response = self._call_llm(prompt, system="You break Text-to-SQL questions into sub-questions.")
        if not response:
            return []

        sub_questions = []
        for line in response.splitlines():
            cleaned = self._clean_sub_question(line)
            if cleaned:
                sub_questions.append(cleaned)
        # Limit to a reasonable number of sub-queries
        return sub_questions[:5]

    def _generate_sub_sql(self, sub_question: str):
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Sub-question:\n{sub_question}\n\n"
            "Write a single SQL query that answers this sub-question. Output only SQL."
        )
        response = self._call_llm(prompt, system="You are a Text-to-SQL assistant. Output only SQL.")
        if not response:
            return None
        sql = bridge.extract_sql(response)
        return sql or None

    def _assemble_final_sql(self, question: str, sub_queries):
        sub_query_lines = []
        for idx, (sub_q, sql) in enumerate(sub_queries, 1):
            sub_query_lines.append(f"{idx}. Sub-question: {sub_q}\n   SQL: {sql}")
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Original question:\n{question}\n\n"
            "Sub-queries:\n" + "\n".join(sub_query_lines) + "\n\n"
            "Produce a single SQL query that answers the original question by combining these sub-queries appropriately. "
            "Use CTEs or subqueries as needed. Output only SQL."
        )
        response = self._call_llm(prompt, system="You are a Text-to-SQL assembler. Output only SQL.")
        if not response:
            return None
        sql = bridge.extract_sql(response)
        return sql or None

    def _direct_sql(self, question: str):
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Write a single SQL query that answers the question. Output only SQL."
        )
        response = self._call_llm(prompt, system="You are a Text-to-SQL assistant. Output only SQL.")
        if not response:
            return ""
        return bridge.extract_sql(response) or ""

    def _call_llm(self, prompt: str, system: str = ""):
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, list):
            return response[0] if response else ""
        return response or ""

    def _clean_sub_question(self, text: str):
        text = text.strip()
        if not text:
            return ""
        # Remove common list markers like "1.", "12)", "-", "*", "•"
        if len(text) > 1 and text[0].isdigit():
            if text[1] == '.' or text[1] == ')':
                text = text[2:].strip()
            elif len(text) > 2 and text[1].isdigit() and text[2] in ('.', ')'):
                text = text[3:].strip()
        if text.startswith(('-', '*', '•')):
            text = text[1:].strip()
        return text