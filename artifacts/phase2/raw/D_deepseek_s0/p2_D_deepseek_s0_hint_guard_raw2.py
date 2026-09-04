"""Parse the 'Hint:' line from the question and restate its constraints as hard requirements before prompting the LLM for SQL."""
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS0HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        main_question, hint_text = self._parse_hint(question)
        hard_requirements = self._format_hard_requirements(hint_text)

        system = (
            "You are an expert SQL query generator. "
            "You must treat the Hard Requirements section as inviolable constraints."
        )
        prompt = f"""Database schema:
{self.schema}

Question:
{main_question}

Hard Requirements (from the Hint in the original question):
{hard_requirements}

Generate a single SQL query that satisfies all Hard Requirements exactly. Return only the SQL query, without any explanation or markdown formatting."""

        raw = self._call_llm(prompt, system)
        sql = bridge.extract_sql(raw)
        if not sql or not sql.strip():
            # Fallback: if extraction failed but the raw output is SQL-like, use it directly.
            sql = raw.strip()
        return sql.strip()

    def _call_llm(self, prompt: str, system: str) -> str:
        responses = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(responses, list):
            if responses:
                return str(responses[0])
            return ""
        return str(responses)

    def _parse_hint(self, question: str):
        """Split question into main question and hint text."""
        if not question:
            return question, ""

        lines = question.splitlines()
        hint_line_idx = None
        for i, line in enumerate(lines):
            if re.match(r'^Hint\s*:\s?', line.strip(), flags=re.IGNORECASE):
                hint_line_idx = i
                break

        if hint_line_idx is not None:
            question_lines = lines[:hint_line_idx]
            hint_lines = lines[hint_line_idx:]

            first_line = hint_lines[0]
            first_colon = first_line.find(':')
            if first_colon != -1:
                first_rest = first_line[first_colon + 1:].strip()
            else:
                first_rest = first_line.strip()

            rest_lines = [l.strip() for l in hint_lines[1:] if l.strip()]
            hint_parts = [first_rest] + rest_lines
            hint_text = "\n".join(p for p in hint_parts if p).strip()

            main_question = "\n".join(question_lines).strip()
            return main_question, hint_text

        # Fallback for inline "Hint:" text
        match = re.split(r'\s*Hint\s*:\s*', question, maxsplit=1, flags=re.IGNORECASE)
        if len(match) == 2:
            return match[0].strip(), match[1].strip()

        return question, ""

    def _format_hard_requirements(self, hint_text: str) -> str:
        if not hint_text:
            return "- No additional constraints provided."

        parts = [p.strip() for p in hint_text.splitlines() if p.strip()]
        if not parts:
            return "- No additional constraints provided."

        bullets = [f"- {p}" for p in parts]
        return "\n".join(bullets)