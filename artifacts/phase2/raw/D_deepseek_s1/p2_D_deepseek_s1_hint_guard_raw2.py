"""Parse a 'Hint:' line from the question and restate its constraints as hard requirements to guide SQL generation."""
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS1HintGuard(SQLHarness):
    """Harness that extracts hint constraints from the question before SQL generation."""

    def solve(self, question: str) -> str:
        hints = self._parse_hints(question)
        prompt = self._build_prompt(question, hints)

        raw_response = self.llm(
            prompt,
            system=(
                "You are an expert SQL writer. The hard requirements from the question's Hint line "
                "must be satisfied exactly. Output only SQL."
            ),
            temperature=0.0,
            n=1,
        )
        response_text = self._to_text(raw_response)
        sql = bridge.extract_sql(response_text).strip()
        if not sql:
            sql = response_text.strip()

        # Avoid executing anything that could mutate data; only SELECT/WITH are expected.
        if not re.match(r"^\s*(select|with)\b", sql, re.IGNORECASE):
            return sql

        # Validate the generated SQL if possible, and retry once on an execution error.
        try:
            result = self.execute(sql)
        except Exception:
            return sql

        if result.get("ok"):
            return sql

        error_msg = str(result.get("error", "unknown execution error"))
        retry_prompt = (
            prompt
            + f"\n\nYour previous SQL:\n{sql}\nreturned this error:\n{error_msg}\n"
            + "Write a corrected SQL query that still satisfies all hard requirements."
        )
        raw_retry = self.llm(
            retry_prompt,
            system=(
                "You are an expert SQL writer. Fix the SQL error and obey all hard requirements "
                "from the question's Hint line. Output only SQL."
            ),
            temperature=0.0,
            n=1,
        )
        retry_text = self._to_text(raw_retry)
        retry_sql = bridge.extract_sql(retry_text).strip()
        if not retry_sql:
            retry_sql = retry_text.strip()
        return retry_sql

    def _parse_hints(self, question: str) -> list[str]:
        """Return all hint contents from lines beginning with 'Hint:' (case-insensitive)."""
        hints = []
        for line in question.splitlines():
            match = re.match(r"^\s*hint\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                hint = match.group(1).strip()
                if hint:
                    hints.append(hint)
        return hints

    def _build_prompt(self, question: str, hints: list[str]) -> str:
        if hints:
            hint_block = (
                "Hard requirements extracted from the question's Hint line "
                "(all are mandatory and must be satisfied):\n"
                + "\n".join(f"- {hint}" for hint in hints)
            )
        else:
            hint_block = "No extra hard requirements were provided."

        return (
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"{hint_block}\n\n"
            "Write a single SQL query that answers the question and satisfies all hard requirements. "
            "Output only the SQL query, no explanation."
        )

    @staticmethod
    def _to_text(llm_result) -> str:
        """Best-effort conversion of an LLM result to a string."""
        if isinstance(llm_result, list):
            if llm_result:
                return str(llm_result[0])
            return ""
        if isinstance(llm_result, dict):
            for key in ("text", "message", "content", "completion"):
                if key in llm_result and llm_result[key] is not None:
                    return str(llm_result[key])
            return str(llm_result)
        return str(llm_result)