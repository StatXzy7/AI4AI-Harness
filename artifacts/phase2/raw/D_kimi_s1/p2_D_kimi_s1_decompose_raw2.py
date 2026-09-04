"""Harness that breaks the question into ordered sub-questions, answers each with its own small LLM call (grounded by executing any partial SQL it proposes), and then assembles the final SQL from the accumulated sub-answers."""

import re
from typing import Any, Dict, List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1Decompose(SQLHarness):
    """Decompose -> per-step answer -> assemble, wrapping a frozen weak solver.

    The strategy lives in the control flow: one planning call produces an
    ordered list of sub-questions; each sub-question is resolved sequentially
    by its own small LLM call, and any SQL it proposes is executed so that
    later steps see concrete intermediate values; a final call assembles the
    answer SQL from the accumulated trace, followed by a bounded
    execute-and-repair loop.
    """

    MAX_SUBQUESTIONS = 6
    MAX_ROWS_SHOWN = 8
    REPAIR_ATTEMPTS = 2

    # ------------------------------------------------------------------ API
    def solve(self, question: str) -> str:
        # Step 1: plan -- break the question into ordered sub-questions.
        sub_questions = self._decompose(question)

        # Step 2: answer each sub-question with its own small LLM call,
        # threading the accumulated results forward through the trace.
        trace: List[Dict[str, Any]] = []
        for idx, sub_q in enumerate(sub_questions, 1):
            trace.append(self._answer_subquestion(question, sub_q, idx, trace))

        # Step 3: assemble the final SQL from the full trace.
        sql = self._assemble(question, trace)

        # Step 4: bounded execution / repair loop.
        for _ in range(self.REPAIR_ATTEMPTS):
            if not sql:
                break
            result = self._safe_execute(sql)
            if result.get("ok"):
                break
            sql = self._repair(question, sql, result.get("error", ""), trace)

        return sql

    # ------------------------------------------------------------- internals
    def _decompose(self, question: str) -> List[str]:
        system = (
            "You are a careful query planner for a Text-to-SQL system. "
            "You split complex questions into a short ordered plan."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Break the question into 2 to {self.MAX_SUBQUESTIONS} ordered sub-questions such that "
            "answering them one after another provides every value and relation needed to write the "
            "final SQL. Make intermediate lookups (IDs, names, extrema, filtered sets) explicit; the "
            "last sub-question must ask for exactly what the original question wants returned.\n\n"
            "Output ONLY a numbered list, one sub-question per line:\n"
            "1. ...\n"
            "2. ..."
        )
        text = self._call_llm(prompt, system=system)
        sub_questions = self._parse_subquestions(text)
        if not sub_questions:
            sub_questions = [question]
        return sub_questions[: self.MAX_SUBQUESTIONS]

    def _answer_subquestion(
        self,
        question: str,
        sub_q: str,
        idx: int,
        trace: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        system = (
            "You are a SQL expert solving exactly one step of a larger plan. "
            "Stay strictly within the scope of the current sub-question."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Original question: {question}\n\n"
            f"{self._format_trace(trace)}\n\n"
            f"Current sub-question {idx}: {sub_q}\n\n"
            "Answer ONLY this sub-question.\n"
            "- If it needs data from the database, output one SQL query in a