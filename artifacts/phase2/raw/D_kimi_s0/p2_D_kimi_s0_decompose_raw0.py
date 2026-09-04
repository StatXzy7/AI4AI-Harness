"""Decompose the question into ordered sub-questions, answer each with a small LLM call, and assemble the final SQL from the accumulated sub-answers."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS0Decompose(SQLHarness):
    """Text-to-SQL harness driven by ordered question decomposition.

    Control flow (implemented explicitly, not just in the prompt):
      1. Decompose  -- one LLM call splits the question into an ordered
                       list of sub-questions.
      2. Answer     -- each sub-question is answered in order by its own
                       small LLM call, with all previous sub-answers
                       threaded forward as context.
      3. Assemble   -- a final LLM call combines the original question,
                       the plan, and every sub-answer into one SQL query.
      4. Validate   -- the SQL is executed; on failure a bounded repair
                       loop re-prompts the LLM with the database error.
    """

    MAX_SUBQUESTIONS = 6
    MAX_REPAIR_ATTEMPTS = 2

    # ------------------------------------------------------------------ #
    # Main entry point                                                    #
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        # Step 1: decompose the question into ordered sub-questions.
        sub_questions = self._decompose(question)

        # Step 2: answer each sub-question in order with a small LLM call.
        sub_answers = []
        for index, sub_question in enumerate(sub_questions, start=1):
            answer = self._answer_subquestion(
                question=question,
                sub_questions=sub_questions,
                index=index,
                sub_answers=sub_answers,
            )
            sub_answers.append((sub_question, answer))

        # Step 3: assemble the final SQL from the question and sub-answers.
        raw_sql = self._assemble(question, sub_answers)
        sql = bridge.extract_sql(raw_sql)

        # Fallback: if assembly yielded nothing usable, generate directly.
        if not sql:
            sql = bridge.extract_sql(self._direct(question))

        # Step 4: execute and, if necessary, repair the query.
        sql = self._validate_and_repair(question, sql)
        return sql

    # ------------------------------------------------------------------ #
    # Step 1: decomposition                                               #
    # ------------------------------------------------------------------ #

    def _decompose(self, question: str) -> list:
        system = (
            "You are a query planner for a text-to-SQL system. Break the "
            "user's question into an ordered list of at most "
            f"{self.MAX_SUBQUESTIONS} simple sub-questions that, when "
            "answered in order, make it straightforward to write the final "
            "SQL query. Output ONLY the numbered list, one sub-question "
            "per line, with no extra commentary."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Ordered sub-questions:"
        )
        text = self._call_llm(prompt, system=system)
        sub_questions = self._parse_numbered_list(text)
        return sub_questions[: self.MAX_SUBQUESTIONS]

    @staticmethod
    def _parse_numbered_list(text: str) -> list:
        items = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^(?:\d+[\.\):\-]?|[-*•])\s*(.+)$", line)
            if match:
                item = match.group(1).strip().strip('"').strip()
                if item:
                    items.append(item)
        if not items and text.strip():
            # Fallback: treat every non-empty line as a sub-question.
            items = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return items

    # ------------------------------------------------------------------ #
    # Step 2: per-sub-question answering                                  #
    # ------------------------------------------------------------------ #

    def _answer_subquestion(
        self,
        question: str,
        sub_questions: list,
        index: int,
        sub_answers: list,
    ) -> str:
        sub_question = sub_questions[index - 1]
        system = (
            "You are a careful data analyst. Answer the current sub-question "
            "concisely and concretely, referencing specific tables, columns, "
            "literal values, or SQL fragments from the schema whenever "
            "possible. Do not write the final query yet."
        )
        plan_lines = [
            f"{i}. {sq}" for i, sq in enumerate(sub_questions, start=1)
        ]
        prompt_parts = [
            f"Database schema:\n{self.schema}",
            f"Original question: {question}",
            "Plan:\n" + "\n".join(plan_lines),
        ]
        if sub_answers:
            history_lines = [
                f"Sub-question {i}: {sq}\nAnswer {i}: {ans}"
                for i, (sq, ans) in enumerate(sub_answers, start=1)
            ]
            prompt_parts.append(
                "Answers so far:\n" + "\n\n".join(history_lines)
            )
        prompt_parts.append(
            f"Current sub-question ({index}/{len(sub_questions)}): "
            f"{sub_question}"
        )
        prompt_parts.append("Answer:")
        return self._call_llm("\n\n".join(prompt_parts), system=system).strip()

    # ------------------------------------------------------------------ #
    # Step 3: assembly                                                    #
    # ------------------------------------------------------------------ #

    def _assemble(self, question: str, sub_answers: list) -> str:
        system = (
            "You are an expert SQL generator. Using the decomposition and "
            "the sub-question answers, write a single SQL query that answers "
            "the original question. Output ONLY the SQL query."
        )
        prompt_parts = [
            f"Database schema:\n{self.schema}",
            f"Question: {question}",
        ]
        if sub_answers:
            qa_lines = [
                f"Sub-question {i}: {sq}\nAnswer {i}: {ans}"
                for i, (sq, ans) in enumerate(sub_answers, start=1)
            ]
            prompt_parts.append(
                "Decomposition and answers:\n" + "\n\n".join(qa_lines)
            )
        prompt_parts.append("SQL query:")
        return self._call_llm("\n\n".join(prompt_parts), system=system)

    def _direct(self, question: str) -> str:
        system = (
            "You are an expert SQL generator. Write a single SQL query that "
            "answers the question. Output ONLY the SQL query."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL query:"
        )
        return self._call_llm(prompt, system=system)

    # ------------------------------------------------------------------ #
    # Step 4: validation and repair                                       #
    # ------------------------------------------------------------------ #

    def _validate_and_repair(self, question: str, sql: str) -> str:
        if not sql:
            return sql
        current = sql
        attempts = 0
        while True:
            result = self.execute(current)
            if result.get("ok") or attempts >= self.MAX_REPAIR_ATTEMPTS:
                return current
            attempts += 1
            error = result.get("error") or "unknown error"
            repaired = bridge.extract_sql(
                self._repair(question, current, error)
            )
            if not repaired or repaired == current:
                return current
            current = repaired

    def _repair(self, question: str, sql: str, error: str) -> str:
        system = (
            "You are an expert SQL debugger. Fix the SQL query so it "
            "executes without errors while still answering the question. "
            "Output ONLY the corrected SQL query."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Faulty SQL:\n{sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Corrected SQL query:"
        )
        return self._call_llm(prompt, system=system)

    # ------------------------------------------------------------------ #
    # LLM plumbing                                                        #
    # ------------------------------------------------------------------ #

    def _call_llm(self, prompt: str, system: str = "") -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""
        return "" if response is None else str(response)