"""Harness that parses the Hint line from the question and enforces it as explicit hard requirements before SQL generation."""
from ..harness_base import SQLHarness
from .. import bridge

import re


class P2P2CQwenS2HintGuard(SQLHarness):
    """Text-to-SQL harness that makes Hint constraints non-negotiable."""

    MAX_ATTEMPTS = 2

    def solve(self, question: str) -> str:
        question = question or ""
        schema = str(getattr(self, "schema", "") or "")

        hint, cleaned_question = self._extract_hint(question)
        question_text = cleaned_question or question.strip()
        hard_requirements = self._build_hard_requirements(hint)

        system = ""
        base_prompt = (
            "Read the HARD REQUIREMENTS below before writing SQL.\n"
            "They are mandatory and override any conflicting wording.\n\n"
            f"{hard_requirements}\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question_text}\n\n"
            "Write one executable SQL query that answers the question while satisfying every hard requirement.\n"
            "Return only the SQL query, without markdown, comments, or explanations."
        )

        final_sql = ""
        last_error = ""

        for attempt in range(self.MAX_ATTEMPTS):
            prompt = base_prompt
            if attempt > 0 and last_error:
                prompt += (
                    "\n\nA previous attempt failed.\n"
                    f"Error: {last_error}\n"
                    "Regenerate a corrected SQL query that still satisfies all hard requirements."
                )

            try:
                response = self.llm(prompt, system=system, temperature=0.0, n=1)
            except Exception as exc:
                last_error = f"LLM call failed: {exc}"
                continue

            text = self._llm_text(response)

            try:
                sql = bridge.extract_sql(text)
            except Exception:
                sql = None

            if not sql:
                last_error = "No SQL statement could be extracted from the model response."
                continue

            sql = sql.strip()
            final_sql = sql

            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if isinstance(result, dict):
                if result.get("ok"):
                    return sql
                last_error = str(result.get("error") or "SQL execution failed.")
            else:
                if result:
                    return sql
                last_error = "SQL execution failed."

        return final_sql

    def _extract_hint(self, question: str):
        if not question:
            return None, ""

        hint_parts = []
        remaining_lines = []

        for line in question.splitlines():
            match = re.match(
                r"^\s*(?:[-*•\d\.\s]+)?hint\s*[:\-–—]\s*(?P<hint>.+?)\s*$",
                line,
                flags=re.IGNORECASE,
            )
            if match and match.group("hint").strip():
                hint_parts.append(match.group("hint").strip())
            else:
                remaining_lines.append(line)

        if hint_parts:
            hint = " ".join(hint_parts).strip()
            cleaned = "\n".join(remaining_lines).strip()
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
            return hint, cleaned

        match = re.search(
            r"\bhint\s*[:\-–—]\s*(?P<hint>[^\n]+)",
            question,
            flags=re.IGNORECASE,
        )
        if match:
            hint = match.group("hint").strip()
            cleaned = question.replace(match.group(0), " ", 1)
            cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
            return hint, cleaned

        return None, question.strip()

    def _build_hard_requirements(self, hint: str) -> str:
        lines = ["HARD REQUIREMENTS"]

        if hint:
            constraints = self._split_hint_constraints(hint)
            lines.append("The following Hint constraints are mandatory and must be implemented in the SQL:")
            for idx, constraint in enumerate(constraints, start=1):
                lines.append(f"{idx}. {constraint}")

            next_idx = len(constraints) + 1
            lines.append(f"{next_idx}. Hint: {hint}")
            lines.append(f"{next_idx + 1}. Do not omit, weaken, or reinterpret any constraint from the hint.")
        else:
            lines.append("1. Produce a valid SQL query that answers the question.")

        lines.append("Return only one executable SQL statement.")
        return "\n".join(lines)

    def _split_hint_constraints(self, hint: str):
        parts = re.split(r";|\n|(?<=\.)\s+", hint)
        cleaned = []

        for part in parts:
            item = part.strip(" .;")
            if item:
                cleaned.append(item)

        return cleaned or [hint]

    def _llm_text(self, response) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, bytes):
            return response.decode("utf-8", "ignore")
        if isinstance(response, list):
            return "\n".join(self._llm_text(item) for item in response)
        if isinstance(response, dict):
            for key in ("text", "content", "output", "message", "result", "completion"):
                if key in response:
                    return self._llm_text(response[key])

            choices = response.get("choices")
            if choices is not None:
                return self._llm_text(choices)

            return str(response)

        return str(response)