"""Samples three SQL queries from the LLM, executes each parsed SQL, and returns the SQL whose execution result is the majority."""
from ..harness_base import SQLHarness
from .. import bridge
import json
from collections import Counter


class P2P2DDeepseekS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        responses = self.llm(prompt, system="", temperature=0.7, n=3)

        # Normalize the LLM response into a list of strings.
        if isinstance(responses, str):
            responses = [responses]
        elif isinstance(responses, dict):
            choices = responses.get("choices", [])
            responses = []
            for choice in choices:
                if isinstance(choice, dict):
                    text = choice.get("text", "")
                    if not text:
                        message = choice.get("message", {})
                        if isinstance(message, dict):
                            text = message.get("content", "")
                    responses.append(text)
                else:
                    responses.append(str(choice))
        elif not isinstance(responses, list):
            responses = [str(responses)]

        parsed_sqls = []
        for text in responses:
            sql = bridge.extract_sql(text)
            if sql:
                parsed_sqls.append(sql)

        successful = []
        for sql in parsed_sqls:
            exec_result = self.execute(sql)
            if exec_result.get("ok"):
                rows = exec_result.get("rows", [])
                signature = self._result_signature(rows)
                successful.append((sql, signature))

        if not successful:
            return parsed_sqls[0] if parsed_sqls else ""

        counts = Counter(signature for _, signature in successful)
        majority_signature, majority_count = counts.most_common(1)[0]

        # With three attempts, two or more identical results constitute a majority.
        if majority_count >= 2:
            for sql, signature in successful:
                if signature == majority_signature:
                    return sql

        # Fallback if no majority is present.
        return successful[0][0]

    def _build_prompt(self, question: str) -> str:
        return (
            "Given the following database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query that answers the question. Return only the SQL query, without explanation."
        )

    @staticmethod
    def _result_signature(rows) -> str:
        """Create a canonical, order-insensitive signature for a result set."""
        serialized = []
        for row in rows:
            if isinstance(row, dict):
                normalized = json.dumps(row, sort_keys=True, default=str)
            else:
                normalized = json.dumps(row, sort_keys=True, default=str)
            serialized.append(normalized)
        serialized.sort()
        return json.dumps(serialized, sort_keys=True)