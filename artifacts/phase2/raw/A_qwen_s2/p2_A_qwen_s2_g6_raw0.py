"""Generate a SQL query, execute it, and repair it using execution errors."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        system = "You are an expert SQL engineer. Return only one executable SQL query."
        task = (
            "Using the schema below, write one SQL query that answers the question.\n"
            "Return only SQL text, no markdown and no explanation."
        )

        def build_prompt(extra: str = "") -> str:
            parts = [task, "", "Schema:", schema, "", "Question:", question]
            if extra:
                parts.extend(["", extra])
            parts.append("")
            parts.append("SQL:")
            return "\n".join(parts)

        def normalize_response(response) -> str:
            if isinstance(response, list):
                response = response[0] if response else ""
            return str(response or "")

        def extract_sql(raw_text: str) -> str:
            if not raw_text:
                return ""

            try:
                extracted = bridge.extract_sql(raw_text)
            except Exception:
                extracted = None

            sql = (extracted or raw_text).strip()

            if "