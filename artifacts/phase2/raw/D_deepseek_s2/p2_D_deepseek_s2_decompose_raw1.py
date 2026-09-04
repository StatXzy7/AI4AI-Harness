"""Break a Text-to-SQL question into ordered sub-questions, solve each with a focused LLM call, and assemble the final SQL."""
import json
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2Decompose(SQLHarness):
    def _llm_text(self, prompt: str, system: str = "") -> str:
        result = self.llm(prompt, system=system, temperature=0.0, n=1)
        if result is None:
            return ""
        if isinstance(result, list):
            return str(result[0]) if result else ""
        return str(result)

    def _parse_sub_questions(self, text: str):
        text = text.strip()
        if not text:
            return []

        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except Exception:
            pass

        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(text[start:end + 1])
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except Exception:
                pass

        marker_items = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r'^\s*(?:\d+[\.\)]|[-*])\s*', line)
            if m:
                cleaned = line[m.end():].strip()
                if cleaned:
                    marker_items.append(cleaned)
        if marker_items:
            return marker_items

        return [text]

    def solve(self, question: str) -> str:
        schema = self.schema

        decomposition_prompt = (
            "You are an expert Text-to-SQL planner. Given a database schema and a user question, "
            "break the question into a small number of ordered sub-questions (usually 2-5). "
            "Each sub-question should be answerable by a single, simple SQL query or subquery. "
            "Return ONLY a JSON array of strings, e.g. [\"Find ...\", \"Then ...\"].\n\n"
            f"Schema:\n{schema}\n\nQuestion:\n{question}"
        )
        decomposition_output = self._llm_text(decomposition_prompt)
        sub_questions = self._parse_sub_questions(decomposition_output)
        if not sub_questions:
            sub_questions = [question]

        sub_solutions = []
        for idx, sub_question in enumerate(sub_questions, 1):
            sub_prompt = (
                "You are a SQL expert. Write a standalone SQL query for the sub-question below "
                "using the provided schema. Return only the SQL query, without explanation or markdown.\n\n"
                f"Schema:\n{schema}\n\nOriginal question:\n{question}\n\nSub-question {idx}:\n{sub_question}"
            )
            sub_output = self._llm_text(sub_prompt)
            sub_sql = bridge.extract_sql(sub_output)
            if not sub_sql:
                sub_sql = sub_output.strip().rstrip(";")
            sub_solutions.append((sub_question, sub_sql))

        solved_parts = "\n\n".join(
            f"Sub-question {i}:\n{sq}\nSQL:\n{sql}"
            for i, (sq, sql) in enumerate(sub_solutions, 1)
        )
        assembly_prompt = (
            "You are a SQL expert. Given the original question, the database schema, and the following "
            "solved sub-questions, write a single final SQL query that answers the original question. "
            "You may use subqueries, CTEs, or JOINs as needed. Return only the final SQL query, without explanation or markdown.\n\n"
            f"Schema:\n{schema}\n\nOriginal question:\n{question}\n\nSolved sub-questions:\n{solved_parts}"
        )
        final_output = self._llm_text(assembly_prompt)
        final_sql = bridge.extract_sql(final_output)
        if not final_sql:
            final_sql = final_output.strip().rstrip(";")
        if not final_sql and sub_solutions:
            final_sql = sub_solutions[-1][1]
        return final_sql or "SELECT 1"