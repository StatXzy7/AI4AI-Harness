"""Repair-loop harness that feeds SQL execution errors back to the LLM for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

MAX_REPAIRS = 3


class P2P2AMinimaxS1G5(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""

        system = (
            "You are a precise Text-to-SQL generator. "
            "Given a database schema and a natural language question, "
            "produce exactly one syntactically correct SQL query. "
            "Use only tables and columns present in the schema. "
            "Output ONLY the SQL statement with no prose, no markdown fences, no commentary."
        )

        prompt = (
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Return a single SQL statement that answers the question."
        )

        current_sql = self.llm(
            prompt,
            system=system,
            temperature=0.0,
            n=1,
        )

        current_sql = bridge.extract_sql(current_sql)

        last_error = ""
        for attempt in range(MAX_REPAIRS):
            result = self.execute(current_sql)
            if result.get("ok"):
                return current_sql

            last_error = (
                result.get("error")
                or result.get("message")
                or "unknown execution error"
            )

            if not schema:
                break

            repair_prompt = (
                f"Database schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                f"Previously generated SQL:\n{current_sql}\n\n"
                f"That SQL failed to execute with the following error:\n"
                f"{last_error}\n\n"
                "Diagnose the problem and return a corrected SQL statement that "
                "will execute successfully. "
                "Output ONLY the SQL statement with no prose, no markdown fences, "
                "no commentary."
            )

            repaired = self.llm(
                repair_prompt,
                system=system,
                temperature=0.0,
                n=1,
            )

            candidate = bridge.extract_sql(repaired)
            if not candidate or candidate.strip() == current_sql.strip():
                if attempt == MAX_REPAIRS - 1:
                    break
                continue

            current_sql = candidate

        return current_sql if current_sql else ""