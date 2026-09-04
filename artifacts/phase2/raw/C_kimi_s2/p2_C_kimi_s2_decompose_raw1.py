"""Decompose each question into ordered sub-questions, answer every sub-question with its own small LLM call, then assemble the SQL fragments into one execution-verified final query."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2Decompose(SQLHarness):
    """P2P2C-style staged harness around the frozen Kimi-S2 solver.

    The decomposition strategy lives in the control flow, not only in prompts:
      1. PLAN  -- one LLM call splits the question into an ordered list of
                  sub-questions, parsed structurally from the numbered list.
      2. SOLVE -- each sub-question is answered by its own small LLM call,
                  conditioned on the schema and on every fragment produced so
                  far; runnable fragments are execution-checked and repaired.
      3. CODE  -- a dedicated assembly call merges the ordered fragments into
                  one final SQL query.
      4. CHECK -- the final SQL is executed; on failure it is repaired with
                  the database error message, for a bounded number of tries.
    """

    MAX_SUBQUESTIONS = 6
    STEP_REPAIR_TRIES = 1
    FINAL_REPAIR_TRIES = 3

    _NUM_PREFIX = re.compile(r"^\s*(?:step\s*)?\d+\s*[.):]\s*", re.IGNORECASE)
    _BULLET_PREFIX = re.compile(r"^\s*[-*•]\s*")
    _FULL_QUERY = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

    # ------------------------------------------------------------------
    # entry point
    # ------------------------------------------------------------------
    def solve(self, question: str) -> str:
        # Stage 1: ordered decomposition of the question.
        sub_questions = self._decompose(question)

        # Stage 2: solve each sub-question in order, threading previously
        # produced fragments through the prompts.
        solved_steps = []
        for index, sub_question in enumerate(sub_questions, start=1):
            fragment = self._solve_subquestion(
                question=question,
                sub_question=sub_question,
                step_index=index,
                total_steps=len(sub_questions),
                solved_steps=solved_steps,
            )
            fragment = self._verify_fragment(question, sub_question, fragment)
            solved_steps.append((sub_question, fragment))

        # Stage 3: assemble all fragments into the final SQL.
        final_sql = self._assemble(question, solved_steps)
        if not final_sql:
            final_sql = self._direct_generate(question)

        # Stage 4: execution-verified repair of the assembled query.
        return self._repair_final(question, solved_steps, final_sql)

    # ------------------------------------------------------------------
    # stage 1: decomposition
    # ------------------------------------------------------------------
    def _decompose(self, question):
        system = (
            "You are a query planner for Text-to-SQL. You break complex "
            "questions into simple, ordered sub-questions."
        )
        prompt = (
            "Given the database schema and the question, break the question "
            f"into an ordered list of at most {self.MAX_SUBQUESTIONS} small "
            "sub-questions that, when answered in order, yield the final SQL "
            "query.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Rules:\n"
            "- Each sub-question must be answerable with one small SQL query "
            "or a single SQL clause.\n"
            "- Order the sub-questions so that later steps may build on "
            "earlier ones.\n"
            "- Output ONLY the numbered list, one sub-question per line, "
            'e.g. "1. ...".\n\n'
            "Sub-questions:"
        )
        response = self._ask(prompt, system)
        steps = self._parse_numbered_list(response)
        if not steps:
            steps = [question]
        return steps[: self.MAX_SUBQUESTIONS]

    @classmethod
    def _parse_numbered_list(cls, text):
        numbered, bulleted = [], []
        for raw_line in str(text).splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if cls._NUM_PREFIX.match(line):
                numbered.append(cls._NUM_PREFIX.sub("", line).strip())
            elif cls._BULLET_PREFIX.match(line):
                bulleted.append(cls._BULLET_PREFIX.sub("", line).strip())
        return [step for step in (numbered or bulleted) if step]

    # ------------------------------------------------------------------
    # stage 2: per-step solving
    # ------------------------------------------------------------------
    def _solve_subquestion(self, question, sub_question, step_index,
                           total_steps, solved_steps):
        system = (
            "You are a careful SQL engineer solving one step of a larger "
            "Text-to-SQL problem at a time."
        )
        prior_block = ""
        if solved_steps:
            prior_lines = []
            for i, (prev_q, prev_frag) in enumerate(solved_steps, start=1):
                prior_lines.append(
                    f"Step {i}: {prev_q}\nStep {i} SQL fragment:\n{prev_frag}"
                )
            prior_block = (
                "Previously solved steps (reuse their fragments when "
                "useful):\n" + "\n\n".join(prior_lines) + "\n\n"
            )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Overall question: {question}\n\n"
            f"{prior_block}"
            f"You are now solving step {step_index} of {total_steps}:\n"
            f"{sub_question}\n\n"
            "Write ONLY the SQL fragment that answers this step (a small "
            "complete SELECT, or a clause such as JOIN / WHERE / GROUP BY / "
            "ORDER BY), consistent with the schema. Output it in a