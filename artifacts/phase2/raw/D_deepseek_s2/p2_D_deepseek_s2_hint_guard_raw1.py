"""Parses the Hint line from the question and restates its constraints as hard requirements before generating SQL."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        hint_lines = []
        clean_lines = []

        for line in question.splitlines():
            match = re.match(r"^\s*Hint:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
            if match:
                hint_lines.append(match.group(1).strip())
            else:
                clean_lines.append(line)

        clean_question = "\n".join(clean_lines).strip()
        if not clean_question:
            clean_question = question.strip()

        if hint_lines:
            hints_text = "\n".join(f"- {hint}" for hint in hint_lines)
        else:
            hints_text = "- (No additional hint constraints were provided.)"

        prompt = (
            "You are a strict Text-to-SQL generator.\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{clean_question}\n\n"
            "Hard requirements parsed from the Hint line. "
            "You MUST satisfy every one of these constraints in the SQL:\n"
            f"{hints_text}\n\n"
            "Generate a single SQL SELECT statement that answers the question and satisfies all hard requirements. "
            "Use only the tables and columns present in the schema. "
            "Return only the SQL statement without any markdown fences or explanation."
        )

        response = self.llm(prompt, system="", temperature=0.0, n=1)

        if isinstance(response, list):
            response = response[0] if response else ""

        sql = bridge.extract_sql(response)
        return sql.strip() if sql else ""