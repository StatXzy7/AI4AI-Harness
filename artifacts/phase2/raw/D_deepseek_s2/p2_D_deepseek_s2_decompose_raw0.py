"""Break a Text-to-SQL question into ordered sub-questions, answer each by generating and executing a small SQL query, then assemble the final SQL query."""
import json
import re
from ..harness_base import SQLHarness
from .. import bridge

class P2P2DDeepseekS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        subquestions = self._decompose(question)
        intermediate = []
        for subq in subquestions:
            sql = self._generate_sub_sql(subq)
            result = self._execute_sql(sql)
            intermediate.append({
                "subquestion": subq,
                "sql": sql,
                "result": result,
            })
        return self._assemble_final_sql(question, intermediate)

    def _decompose(self, question: str):
        prompt = (
            "You are a Text-to-SQL planner. Break the original question into a list of ordered, "
            "simple sub-questions, each independently answerable with a single SQL SELECT query. "
            "Return ONLY a JSON array of strings, with no surrounding text.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Original question: {question}\n\n"
            "Ordered sub-questions (JSON array):"
        )
        raw = self.llm(prompt, system="You are a concise JSON planner.", temperature=0.0, n=1)
        subqs = self._parse_json_list(raw)
        return subqs if subqs else [question]

    def _generate_sub_sql(self, subq: str) -> str:
        prompt = (
            "Write a single SQL query that answers the sub-question below.\n"
            "Return ONLY the SQL query, with no explanation or markdown fences.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Sub-question: {subq}"
        )
        raw = self.llm(prompt, system="You are an expert SQLite SQL writer.", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)
        return sql or "SELECT 1;"

    def _execute_sql(self, sql: str):
        if not sql:
            return {"ok": False, "rows": [], "error": "Empty SQL"}
        try:
            result = self.execute(sql)
            if not isinstance(result, dict):
                return {"ok": False, "rows": [], "error": f"Unexpected execute result: {result}"}
            return result
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    def _assemble_final_sql(self, question: str, intermediate):
        prompt = (
            "You are an expert Text-to-SQL writer. Use the original question, the database schema, "
            "and the intermediate sub-question SQL queries and their results to write one final SQL query "
            "that answers the original question. Prefer composing the intermediate SQL as subqueries/CTEs "
            "rather than hard-coding values. Return ONLY the final SQL query.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Original question: {question}\n\n"
        )
        for item in intermediate:
            result = item["result"]
            if result.get("ok"):
                rows = str(result.get("rows", []))[:2000]
                error = ""
            else:
                rows = ""
                error = result.get("error", "")
            prompt += (
                f"Sub-question: {item['subquestion']}\n"
                f"Generated SQL: {item['sql']}\n"
                f"Execution rows: {rows}\n"
                f"Execution error: {error}\n\n"
            )
        prompt += "Final SQL:"
        raw = self.llm(prompt, system="You are an expert SQLite SQL writer.", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(raw)
        if not final_sql:
            for item in intermediate:
                if item.get("sql"):
                    return item["sql"]
            return "SELECT 1;"
        return final_sql

    @staticmethod
    def _parse_json_list(text):
        if not isinstance(text, str):
            return []
        text = re.sub(r"^