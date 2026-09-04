"""Decompose the question into ordered sub-questions answered by an LLM, then assemble the final SQL."""
from __future__ import annotations

import re

from ..harness_base import SQLHarness
from .. import bridge


SYSTEM_PLANNER = (
    "You are a SQL planning assistant. Given a natural language question and a database schema, "
    "you decompose the question into an ordered list of small, focused sub-questions whose answers "
    "together provide everything needed to construct the final SQL query. "
    "Return ONLY a numbered list (one sub-question per line), nothing else. "
    "Do not write SQL. Do not write explanations. Do not write prose."
)


SYSTEM_SUBQN = (
    "You are a precise assistant that answers one focused sub-question at a time. "
    "Use the provided schema and the original question as context. "
    "Respond with a single concise factual answer in natural language. "
    "Do not write SQL. Do not include commentary."
)


SYSTEM_ASSEMBLER = (
    "You are an expert SQL writer. Given a database schema, the original question, and a list of "
    "Q&A pairs from a planning step, you write the final SQLite-compatible SQL query. "
    "Reason about how the sub-answers combine, then output exactly ONE SQL statement. "
    "Return ONLY the SQL statement, with no markdown fences, no explanations, and no preamble."
)


class P2P2DMinimaxS2Decompose(SQLHarness):
    """Plan -> Sub-question -> Decompose strategy harness."""

    MAX_SUBQN_RETRIES = 1
    MAX_ASSEMBLE_RETRIES = 2

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_numbered_list(text: str) -> list[str]:
        """Parse a numbered list from LLM output, tolerating common formatting variations."""
        items: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            # Strip leading bullets/markers like "1.", "1)", "-", "*", "•"
            m = re.match(r"^(?:[-*•]\s+)?(?:\d+[\.\)]\s*)?(.+)$", line)
            if m:
                candidate = m.group(1).strip()
                if candidate:
                    items.append(candidate)
        return items

    @staticmethod
    def _normalize_plan(raw: list[str], original_question: str) -> list[str]:
        """Ensure the plan is non-empty and contains the original question as a fallback seed."""
        cleaned = [q for q in raw if q and len(q.strip()) > 0]
        if not cleaned:
            return [original_question]
        # Always include the original question as the first seed if not present
        if not any(original_question.strip().lower() == q.strip().lower() for q in cleaned):
            cleaned = [original_question] + cleaned
        return cleaned

    # ------------------------------------------------------------------ #
    # Stage 1: Plan sub-questions
    # ------------------------------------------------------------------ #

    def _plan_subquestions(self, question: str) -> list[str]:
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Decompose the question into an ordered list of small sub-questions."
        )
        raw = self.llm(prompt, system=SYSTEM_PLANNER, temperature=0.0, n=1)
        parsed = self._parse_numbered_list(raw)
        return self._normalize_plan(parsed, question)

    # ------------------------------------------------------------------ #
    # Stage 2: Answer each sub-question
    # ------------------------------------------------------------------ #

    def _answer_subquestions(self, question: str, plan: list[str]) -> list[tuple[str, str]]:
        qa_pairs: list[tuple[str, str]] = []
        for idx, subq in enumerate(plan, start=1):
            prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Original question: {question}\n\n"
                f"Sub-question {idx}/{len(plan)}: {subq}\n\n"
                "Provide a single concise factual answer."
            )
            answer = self.llm(prompt, system=SYSTEM_SUBQN, temperature=0.0, n=1)
            qa_pairs.append((subq, answer.strip()))
        return qa_pairs

    # ------------------------------------------------------------------ #
    # Stage 3: Assemble final SQL
    # ------------------------------------------------------------------ #

    def _assemble_sql(self, question: str, qa_pairs: list[tuple[str, str]]) -> str:
        qa_block = "\n".join(f"Q{i+1}: {q}\nA{i+1}: {a}" for i, (q, a) in enumerate(qa_pairs))
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Original question: {question}\n\n"
            "Planning notes:\n"
            f"{qa_block}\n\n"
            "Write the final SQL query."
        )
        text = self.llm(prompt, system=SYSTEM_ASSEMBLER, temperature=0.0, n=1)
        sql = bridge.extract_sql(text)
        return sql

    def _assemble_with_validation(self, question: str, qa_pairs: list[tuple[str, str]]) -> str:
        """Try to assemble + validate; if extraction/parse fails, retry with explicit instruction."""
        last_sql = ""
        for attempt in range(self.MAX_ASSEMBLE_RETRIES + 1):
            sql = self._assemble_sql(question, qa_pairs) if attempt == 0 else self._assemble_sql_fallback(
                question, qa_pairs, last_error=""
            )
            last_sql = sql
            if not sql:
                continue
            # Validate by attempting execution; if it parses and runs, accept it.
            probe = self.execute(sql)
            if probe.get("ok"):
                return sql
        return last_sql

    def _assemble_sql_fallback(self, question: str, qa_pairs: list[tuple[str, str]], last_error: str) -> str:
        qa_block = "\n".join(f"Q{i+1}: {q}\nA{i+1}: {a}" for i, (q, a) in enumerate(qa_pairs))
        system = SYSTEM_ASSEMBLER + " The previous attempt failed to execute; rewrite the SQL correctly."
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Original question: {question}\n\n"
            "Planning notes:\n"
            f"{qa_block}\n\n"
            f"Previous SQL error (if any): {last_error}\n\n"
            "Write the final SQL query."
        )
        text = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(text)

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        """Plan sub-questions, answer them, then assemble and return the final SQL."""
        # Stage 1: decomposition
        plan = self._plan_subquestions(question)

        # Stage 2: per-sub-question answers
        qa_pairs = self._answer_subquestions(question, plan)

        # Stage 3: assemble + validate
        final_sql = self._assemble_with_validation(question, qa_pairs)

        # Safety net: if everything failed, emit a minimal fallback so the harness returns SOMETHING.
        if not final_sql:
            final_sql = "SELECT 1;"

        return final_sql