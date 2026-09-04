"""Break the question into ordered sub-questions, answer each with a small LLM call against the schema, then assemble, extract, and execution-verify the final SQL."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2Decompose(SQLHarness):
    """Decompose-and-assemble Text-to-SQL harness.

    Control flow:
      1. One LLM call decomposes the question into ordered sub-questions.
      2. Each sub-question is answered by an individual small LLM call,
         conditioned on the schema and the answers to previous sub-questions.
      3. A final LLM call assembles all sub-answers into one SQL query.
      4. The SQL is executed; on failure a single repair call is attempted.
    """

    MAX_SUBQUESTIONS = 6

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        sub_questions = self._decompose(question)

        qa_pairs = []
        for sq in sub_questions:
            answer = self._answer_subquestion(question, sq, qa_pairs)
            qa_pairs.append((sq, answer))

        sql = self._assemble(question, qa_pairs)
        if not sql:
            sql = self._fallback_direct(question)

        # Execution verification with a single repair attempt.
        result = self.execute(sql)
        if not result.get("ok"):
            repaired = self._repair(question, qa_pairs, sql, result.get("error", ""))
            if repaired:
                check = self.execute(repaired)
                if check.get("ok"):
                    sql = repaired

        return sql

    # ------------------------------------------------------------------ #
    # Step 1: decomposition
    # ------------------------------------------------------------------ #
    def _decompose(self, question: str):
        prompt = (
            "You are given a database schema and a natural-language question.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION: {question}\n\n"
            "Break the question into an ordered list of at most "
            f"{self.MAX_SUBQUESTIONS} simple sub-questions such that answering "
            "them in order yields everything needed to write the final SQL query. "
            "Each sub-question must be self-contained, answerable from the schema, "
            "and focused on one step (identify tables/columns, filter values, "
            "compute aggregates, order/limit, etc.).\n"
            "Output ONLY a numbered list, one sub-question per line, e.g.:\n"
            "1. ...\n2. ...\n3. ..."
        )
        text = self.llm(
            prompt,
            system="You decompose database questions into ordered sub-questions.",
            temperature=0.0,
        )
        sub_questions = self._parse_subquestions(text)
        if not sub_questions:
            sub_questions = [question]
        return sub_questions[: self.MAX_SUBQUESTIONS]

    @staticmethod
    def _parse_subquestions(text: str):
        subs = []
        for line in (text or "").splitlines():
            line = line.strip()
            m = re.match(r"^(?:\d+[\.\):\-]?|[-*•])\s*(.+)$", line)
            if m:
                item = m.group(1).strip()
                if item:
                    subs.append(item)
        if not subs:
            # Fallback: treat non-empty lines as sub-questions.
            subs = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        return subs

    # ------------------------------------------------------------------ #
    # Step 2: per-sub-question answering
    # ------------------------------------------------------------------ #
    def _answer_subquestion(self, question: str, sub_question: str, prior_qa) -> str:
        history = ""
        if prior_qa:
            lines = [
                f"Q{i+1}: {sq}\nA{i+1}: {ans}" for i, (sq, ans) in enumerate(prior_qa)
            ]
            history = (
                "PREVIOUS SUB-QUESTIONS AND ANSWERS:\n" + "\n".join(lines) + "\n\n"
            )
        prompt = (
            "You are given a database schema, an overall question, and one "
            "sub-question to answer as a step toward the final SQL query.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"OVERALL QUESTION: {question}\n\n"
            f"{history}"
            f"SUB-QUESTION: {sub_question}\n\n"
            "Answer concisely and concretely: name the exact tables/columns/values "
            "involved and, if applicable, provide the corresponding SQL fragment "
            "(e.g., a WHERE condition, JOIN clause, aggregation, or ORDER BY). "
            "Do NOT write the full query."
        )
        return self.llm(
            prompt,
            system="You answer one database sub-question at a time, precisely.",
            temperature=0.0,
        ).strip()

    # ------------------------------------------------------------------ #
    # Step 3: assembly
    # ------------------------------------------------------------------ #
    def _assemble(self, question: str, qa_pairs) -> str:
        steps = "\n".join(
            f"{i+1}. {sq}\n   Answer: {ans}" for i, (sq, ans) in enumerate(qa_pairs)
        )
        prompt = (
            "You are given a database schema, a question, and the resolved answers "
            "to its ordered sub-questions. Assemble them into ONE final SQL query.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION: {question}\n\n"
            f"RESOLVED SUB-STEPS:\n{steps}\n\n"
            "Write a single syntactically valid SQL query that answers the question. "
            "Output ONLY the SQL query, no explanation, no markdown."
        )
        text = self.llm(
            prompt,
            system="You assemble sub-answers into one correct SQL query.",
            temperature=0.0,
        )
        return bridge.extract_sql(text).strip()

    # ------------------------------------------------------------------ #
    # Repair on execution failure
    # ------------------------------------------------------------------ #
    def _repair(self, question: str, qa_pairs, bad_sql: str, error: str) -> str:
        steps = "\n".join(
            f"{i+1}. {sq}\n   Answer: {ans}" for i, (sq, ans) in enumerate(qa_pairs)
        )
        prompt = (
            "The following SQL query failed. Fix it using the schema and the "
            "resolved sub-steps.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION: {question}\n\n"
            f"RESOLVED SUB-STEPS:\n{steps}\n\n"
            f"FAILING SQL:\n{bad_sql}\n\n"
            f"DATABASE ERROR:\n{error}\n\n"
            "Output ONLY the corrected SQL query, no explanation, no markdown."
        )
        text = self.llm(
            prompt,
            system="You repair SQL queries based on database error messages.",
            temperature=0.0,
        )
        return bridge.extract_sql(text).strip()

    # ------------------------------------------------------------------ #
    # Fallback: direct single-shot SQL
    # ------------------------------------------------------------------ #
    def _fallback_direct(self, question: str) -> str:
        prompt = (
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION: {question}\n\n"
            "Write ONE SQL query answering the question. "
            "Output ONLY the SQL, no explanation, no markdown."
        )
        text = self.llm(
            prompt,
            system="You write correct SQL queries.",
            temperature=0.0,
        )
        return bridge.extract_sql(text).strip()