"""Extracts the Hint line from the question and restates it as mandatory hard requirements before generating SQL."""
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        question_body, hint_text = self._extract_hint(question)
        hard_requirements = self._format_hard_requirements(hint_text)

        system = (
            "You are a precise text-to-SQL assistant. "
            "Treat the hard requirements in the prompt as non-negotiable constraints."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question_body}\n\n"
            f"{hard_requirements}\n\n"
            "Write a single SQL query that answers the question and strictly obeys "
            "every hard requirement above. Output only SQL."
        )

        raw_output = self.llm(prompt, system=system, temperature=0.0, n=1)
        raw_text = self._stringify_llm_output(raw_output)
        return bridge.extract_sql(raw_text)

    def _extract_hint(self, question: str):
        lines = question.splitlines()
        body_lines = []
        hints = []

        for line in lines:
            if line.strip().lower().startswith("hint:"):
                hint_text = line.strip()[5:].strip()
                if hint_text:
                    hints.append(hint_text)
            else:
                body_lines.append(line)

        if hints:
            body = "\n".join(body_lines).strip()
            return body or question, "\n".join(hints).strip()

        # Fallback for inline hints such as "Question text Hint: constraint"
        match = re.search(r"\bHint:\s*(.+)", question, re.IGNORECASE)
        if match:
            hint = match.group(1).strip()
            body = question[: match.start()] + question[match.end() :]
            return body.strip() or question, hint

        return question, ""

    def _format_hard_requirements(self, hint: str) -> str:
        if not hint:
            return "Hard requirements: none."
        return (
            "Hard requirements extracted from the Hint line; "
            "each line is a separate mandatory constraint:\n"
            f"{hint}"
        )

    def _stringify_llm_output(self, output) -> str:
        if isinstance(output, str):
            return output
        if isinstance(output, list):
            if not output:
                return ""
            return self._stringify_llm_output(output[0])
        if isinstance(output, dict):
            for key in ("content", "text", "message"):
                if key in output:
                    return self._stringify_llm_output(output[key])
            if "choices" in output:
                return self._stringify_llm_output(output["choices"])
        return str(output)