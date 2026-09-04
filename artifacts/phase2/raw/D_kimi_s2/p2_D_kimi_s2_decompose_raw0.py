"""Decompose the question into ordered sub-questions, answer each with a small LLM call, then assemble and validate the final SQL."""

from __future__ import annotations

import re
from typing import List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2Decompose(SQLHarness):
    """Plan-then-solve harness around a frozen weak solver.

    The decomposition strategy lives in the control flow, not only in prompts:

      1. ``_decompose`` issues one LLM call that breaks the natural-language
         question into an ordered list of simpler sub-questions, parsed
         structurally from a numbered list in the model output.
      2. ``_solve_subquestion`` issues one small LLM call per sub-question,
         in order, each conditioned on every previously solved step, yielding
         a short rationale plus an optional SQL fragment.
      3. ``_assemble`` issues one LLM call that merges the fragments into a
         single final SQL query over ``self.schema``.
      4. ``_validate_and_repair`` runs the query via ``self.execute`` and, on
         database errors, requests a bounded number of corrected rewrites.
    """

    MAX_SUBQUESTIONS = 6
    MAX_REPAIRS = 2

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # Step 1: ordered decomposition of the question.
        sub_questions = self._decompose(question)

        # Step 2: answer each sub-question with its own small LLM call,
        # threading prior answers forward so later steps build on earlier ones.
        solved: List[Tuple[str, str, str]] = []  # (sub_q, note, fragment)
        for sub_q in sub_questions:
            note, fragment = self._solve_subquestion(question, sub_q, solved)
            solved.append((sub_q, note, fragment))

        # Step 3: assemble the final SQL from all sub-answers.
        sql = self._assemble(question, solved)

        # Step 4: execute and, if necessary, repair within a bounded loop.
        sql = self._validate_and_repair(question, sql)
        return sql

    # ------------------------------------------------------------------ #
    # step 1: decomposition
    # ------------------------------------------------------------------ #
    def _decompose(self, question: str) -> List[str]:
        system = (
            "You are a careful query planner for Text-to-SQL. You break a "
            "complex question into a short ordered list of simpler "
            "sub-questions that can be solved one at a time."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Break the question into an ordered list of at most "
            f"{self.MAX_SUBQUESTIONS} sub-questions such that solving them in "
            "order yields the final SQL query. Requirements:\n"
            "- Each sub-question must be self-contained and reference "
            "concrete tables/columns from the schema where possible.\n"
            "- Each sub-question should be answerable with a small SQL "
            "fragment.\n"
            "- If the question is already simple, output a single "
            "sub-question that restates it.\n\n"
            "Output ONLY a numbered list, one sub-question per line, e.g.:\n"
            "1. <first sub-question>\n"
            "2. <second sub-question>"
        )
        text = self._call_llm(prompt, system=system)
        sub_questions = self._parse_numbered_list(text)
        if not sub_questions:
            # Never run with an empty plan: fall back to the raw question.
            sub_questions = [question]
        return sub_questions[: self.MAX_SUBQUESTIONS]

    @staticmethod
    def _parse_numbered_list(text: str) -> List[str]:
        items: List[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            m = re.match(r"^(?:\d+\s*[\.\):\-]|[-*•])\s*(.+)$", line)
            if m:
                item = m.group(1).strip()
                if item:
                    items.append(item)
        return items

    # ------------------------------------------------------------------ #
    # step 2: per-sub-question solving
    # ------------------------------------------------------------------ #
    def _solve_subquestion(
        self,
        question: str,
        sub_q: str,
        solved: List[Tuple[str, str, str]],
    ) -> Tuple[str, str]:
        system = (
            "You are a precise Text-to-SQL assistant. You answer exactly one "
            "sub-question at a time using the given schema, concisely."
        )
        prior_block = ""
        if solved:
            lines = []
            for i, (prev_q, prev_note, prev_frag) in enumerate(solved, 1):
                entry = f"  {i}. {prev_q}\n     Answer: {prev_note}"
                if prev_frag:
                    entry += f"\n     SQL fragment:\n{prev_frag}"
                lines.append(entry)
            prior_block = (
                "Sub-questions already solved (reuse their results):\n"
                + "\n".join(lines)
                + "\n\n"
            )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Original question: {question}\n\n"
            f"{prior_block}"
            f"Current sub-question: {sub_q}\n\n"
            "Answer ONLY this sub-question in 1-3 short sentences, naming the "
            "tables, columns, join keys, filters or aggregations it requires. "
            "Then provide a minimal SQL fragment implementing JUST this step "
            "(a standalone SELECT if possible, otherwise the relevant clause). "
            "Wrap the SQL in