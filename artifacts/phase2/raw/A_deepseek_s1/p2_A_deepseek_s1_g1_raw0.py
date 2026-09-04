"""Repairs SQL by executing it and feeding execution errors back to the model for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS1G1(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are a SQL generation assistant. Return only a SQL query, no extra text."
        prompt = self._build_initial_prompt(question)
        previous_sql = None
        last_raw = ""
        last_sql = ""

        for _ in range(3):
            last_raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            extracted = bridge.extract_sql(last_raw)
            last_sql = extracted.strip() if extracted else ""

            if last_sql:
                try:
                    result = self.execute(last_sql)
                except Exception as exc:
                    prompt = self._build_repair_prompt(
                        question, f"{type(exc).__name__}: {exc}", last_sql
                    )
                    previous_sql = last_sql
                    continue

                if result.get("ok"):
                    return last_sql

                error = result.get("error") or "Unknown execution error"
                prompt = self._build_repair_prompt(question, error, last_sql)
                previous_sql = last_sql
            else:
                error = "No SQL query was found in the previous response. Output only a SQL query."
                prompt = self._build_repair_prompt(question, error, previous_sql)

        return previous_sql if previous_sql else (last_sql if last_sql else last_raw)

    def _build_initial_prompt(self, question: str) -> str:
        return (
            "Given the following database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query that answers the question. Output only the SQL query."
        )

    def _build_repair_prompt(self, question: str, error: str, previous_sql=None) -> str:
        lines = [
            "Given the following database schema:",
            self.schema,
            "",
            f"Question: {question}",
            "",
            "The previous SQL query was invalid or did not execute successfully.",
        ]
        if previous_sql:
            lines.append(f"Previous SQL:\n{previous_sql}")
        lines.append(f"Execution error:\n{error}")
        lines.append("")
        lines.append("Write a corrected SQL query that answers the question. Output only the SQL query.")
        return "\n".join(lines)