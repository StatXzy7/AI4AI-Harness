"""Parse the question's 'Hint:' line, restate its constraints as hard requirements in the control flow, and guard SQL generation, verification, and repair against them."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2HintGuard(SQLHarness):
    """Hint-Guard harness around a frozen weak Text-to-SQL solver.

    Mechanism:
      1. Parse the 'Hint:' line out of the question (in code, not the prompt).
      2. Restate the hint as an explicit, numbered list of HARD REQUIREMENTS.
      3. Generate SQL only after those requirements are injected into the prompt.
      4. Guard: verify the candidate SQL against the requirements and against
         live execution; repair under the same requirements if either fails.
    """

    MAX_ATTEMPTS = 3  # 1 initial generation + up to 2 guarded repairs.

    # ------------------------------------------------------------------ API
    def solve(self, question: str) -> str:
        # Step 1 (control flow): isolate the Hint line from the question.
        hint = self._extract_hint(question)

        # Step 2 (control flow): restate the hint as hard requirements BEFORE
        # any SQL is written. No hint -> empty block -> plain generation.
        requirements = self._restate_requirements(hint) if hint else ""
        hard_block = self._format_hard_requirements(requirements)

        # Step 3: constrained generation.
        raw = self.llm(
            self._generation_prompt(question, hard_block),
            system=(
                "You are a careful Text-to-SQL engine. You must satisfy every "
                "HARD REQUIREMENT exactly. Output only the SQL query."
            ),
            temperature=0.0,
        )
        sql = bridge.extract_sql(raw) or raw.strip()

        # Step 4: guard loop — verify requirements + execution, repair if needed.
        for attempt in range(1, self.MAX_ATTEMPTS):
            violation = (
                self._check_requirements(question, hard_block, sql)
                if hard_block
                else ""
            )
            if violation:
                sql = self._repair(question, hard_block, sql, violation)
                continue

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            sql = self._repair(
                question,
                hard_block,
                sql,
                "The SQL failed to execute. Database error: "
                + str(result.get("error", "unknown error")),
            )

        return sql

    # ------------------------------------------------------- hint handling
    @staticmethod
    def _extract_hint(question: str) -> str:
        """Return the text of the 'Hint:' line, or '' if none exists."""
        match = re.search(r"(?is)\bhint\s*[:\-]\s*(.+)", question)
        if not match:
            return ""
        hint = match.group(1)
        # The hint ends at the first blank line (or end of string).
        hint = re.split(r"\n\s*\n", hint, maxsplit=1)[0]
        return hint.strip()

    def _restate_requirements(self, hint: str) -> str:
        """Turn raw hint text into a numbered list of hard requirements."""
        prompt = (
            "Rewrite the following Text-to-SQL hint as a numbered list of "
            "HARD REQUIREMENTS that the SQL query MUST satisfy.\n"
            "Rules:\n"
            "- One requirement per line, numbered '1.', '2.', ...\n"
            "- Preserve every table, column, value, and condition mentioned.\n"
            "- Do not add new assumptions and do not drop any constraint.\n"
            "- Output only the numbered list.\n\n"
            f"HINT:\n{hint}\n\n"
            "HARD REQUIREMENTS:"
        )
        out = self.llm(
            prompt,
            system="You restate hints as precise, binding SQL requirements.",
            temperature=0.0,
        )
        return out.strip()

    @staticmethod
    def _format_hard_requirements(requirements: str) -> str:
        if not requirements:
            return ""
        return (
            "HARD REQUIREMENTS (derived from the hint; every one is MANDATORY "
            "and overrides any conflicting instinct):\n"
            f"{requirements}\n"
        )

    # ------------------------------------------------------------- prompts
    def _generation_prompt(self, question: str, hard_block: str) -> str:
        parts = [
            "Given the database schema, write a single SQL query that answers "
            "the question.",
            f"SCHEMA:\n{self.schema}",
        ]
        if hard_block:
            parts.append(hard_block)
        parts.append(f"QUESTION:\n{question}")
        parts.append(
            "Write the SQL now. Return only the SQL, wrapped in a