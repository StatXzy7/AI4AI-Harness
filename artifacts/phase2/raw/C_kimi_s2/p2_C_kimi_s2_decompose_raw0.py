"""Decompose the question into ordered sub-questions, answer each with a small focused LLM call grounded by execution, then assemble the final SQL and repair it against real execution errors."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2Decompose(SQLHarness):
    """Plan-then-solve harness: decompose -> per-sub-question solving -> assembly -> execute-and-repair."""

    MAX_SUBQUESTIONS = 6
    ROW_PREVIEW = 5
    REPAIR_ATTEMPTS = 2

    DECOMPOSE_SYSTEM = (
        "You are a query planner for a Text-to-SQL system. You break a complex "
        "natural-language question into small, ordered, atomic sub-questions."
    )
    SOLVE_SYSTEM = (
        "You are a careful SQLite expert. You answer one sub-question at a time and "
        "write a small, self-contained SQL fragment whenever data must be retrieved."
    )
    ASSEMBLE_SYSTEM = (
        "You are a careful SQLite expert. You combine solved sub-questions into one "
        "correct final SQL query."
    )
    REPAIR_SYSTEM = (
        "You are a careful SQLite expert. You fix SQL queries that failed to execute."
    )

    # ---------------------------------------------------------------- entry point
    def solve(self, question: str) -> str:
        # Stage 1: decompose the question into ordered sub-questions.
        sub_questions = self._decompose(question)

        # Stage 2: answer each sub-question with its own small LLM call, in order,
        # threading the accumulating evidence forward.
        solved = []
        for idx, sub_q in enumerate(sub_questions, start=1):
            solved.append(self._solve_subquestion(question, sub_q, idx, solved))

        # Stage 3: assemble the final SQL from the solved pieces.
        final_sql = self._assemble(question, solved)

        # Stage 4: validate against the database and repair on failure.
        return self._validate_and_repair(question, solved, final_sql)

    # ---------------------------------------------------------- stage 1: decompose
    def _decompose(self, question: str):
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Break this question into an ordered list of at most {self.MAX_SUBQUESTIONS} "
            "atomic sub-questions whose answers, combined in order, yield the final SQL query.\n"
            "Rules:\n"
            "- Each sub-question must be answerable on its own given the previous answers.\n"
            "- Intermediate sub-questions should retrieve the filters, entities, or aggregates "
            "the final query needs.\n"
            "- The last sub-question must ask for exactly the final output columns.\n"
            "- Output ONLY the numbered list, one sub-question per line, e.g.:\n"
            "1. ...\n2. ...\n"
        )
        text = self.llm(prompt, system=self.DECOMPOSE_SYSTEM, temperature=0.0)
        subs = self._parse_numbered_list(text)
        if not subs:  # fallback: treat the whole question as a single sub-question
            subs = [question]
        return subs[: self.MAX_SUBQUESTIONS]

    @staticmethod
    def _parse_numbered_list(text: str):
        items = []
        for line in (text or "").splitlines():
            m = re.match(r"^\s*(?:\d+[\.\):\-]\s*|[-*]\s+)(.+?)\s*$", line)
            if m:
                item = m.group(1).strip()
                if item:
                    items.append(item)
        return items

    # ---------------------------------------------------- stage 2: per-step solving
    def _solve_subquestion(self, question: str, sub_q: str, idx: int, solved):
        history = ""
        if solved:
            blocks = [
                f"Sub-question {p['idx']}: {p['sub_q']}\n"
                f"Answer: {p['note']}\n"
                f"SQL fragment: {p['fragment'] or '(none)'}\n"
                f"Execution: {p['feedback']}"
                for p in solved
            ]
            history = "Previously solved sub-questions:\n" + "\n\n".join(blocks) + "\n\n"

        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Original question: {question}\n\n"
            f"{history}"
            f"Current sub-question ({idx}): {sub_q}\n\n"
            "Answer ONLY this sub-question.\n"
            "- Give a one-sentence answer.\n"
            "- If it requires data from the database, also give a small self-contained SQL "
            "fragment inside a