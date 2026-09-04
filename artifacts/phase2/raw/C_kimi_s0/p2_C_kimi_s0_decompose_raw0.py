"""Decomposition harness: break the question into ordered sub-questions, answer each with its own small LLM call (threading prior answers forward), then assemble, execute, and repair the final SQL."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS0Decompose(SQLHarness):
    """Text-to-SQL via explicit control-flow decomposition.

    Pipeline (implemented in code, not just in the prompt):
      1. _decompose: one LLM call turns the question into an ordered list
         of sub-questions (parsed from a numbered list, with a safe
         fallback to the original question).
      2. _answer_subquestion: each sub-question is answered by its own
         small LLM call that sees the schema plus every previous
         sub-question/answer pair, so later steps build on earlier ones.
      3. _assemble: one LLM call merges the ordered sub-answers into a
         single SQL query.
      4. Validation: the assembled SQL is executed; on failure exactly one
         repair call is issued with the database error message.
    """

    MAX_SUBQUESTIONS = 8

    def solve(self, question: str) -> str:
        # Step 1: decompose into ordered sub-questions.
        sub_questions = self._decompose(question)

        # Step 2: answer each sub-question in order, carrying notes forward.
        notes = []
        for sub_q in sub_questions:
            answer = self._answer_subquestion(question, sub_q, notes)
            notes.append((sub_q, answer))

        # Step 3: assemble the final SQL from the accumulated notes.
        draft = self._assemble(question, notes)
        sql = bridge.extract_sql(draft) or (draft or "").strip()

        # Step 4: validate against the database; one repair attempt on error.
        result = self.execute(sql)
        if not result["ok"]:
            repaired = self._repair(question, notes, sql, result["error"])
            repaired_sql = bridge.extract_sql(repaired) or (repaired or "").strip()
            if repaired_sql:
                sql = repaired_sql
        return sql

    # ------------------------------------------------------------------
    # Step 1: decomposition
    # ------------------------------------------------------------------
    def _decompose(self, question: str):
        system = (
            "You are a query planner for a Text-to-SQL system. You break "
            "complex questions into simple, ordered sub-questions."
        )
        prompt = (
            "Database schema:\n" + self.schema + "\n\n"
            "Question: " + question + "\n\n"
            "Break this question into an ordered list of at most "
            f"{self.MAX_SUBQUESTIONS} sub-questions such that answering them "
            "in order yields everything needed to write the final SQL query. "
            "Each sub-question should identify the tables/columns it needs, "
            "the filter or computation it performs, and how it connects to "
            "the previous step. If the question is already simple, return a "
            "single sub-question restating it.\n"
            "Output ONLY a numbered list, one sub-question per line, e.g.:\n"
            "1. ...\n2. ...\n"
        )
        text = self.llm(prompt, system=system, temperature=0.0)
        sub_questions = self._parse_numbered_list(text)
        if not sub_questions:
            sub_questions = [question]
        return sub_questions[: self.MAX_SUBQUESTIONS]

    @staticmethod
    def _parse_numbered_list(text: str):
        items = []
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(?:\d+\s*[\.\):\-]?|[-*\u2022])\s*(.+)$", line)
            if m:
                item = m.group(1).strip().strip('"')
                if item:
                    items.append(item)
        return items

    # ------------------------------------------------------------------
    # Step 2: per-sub-question answering
    # ------------------------------------------------------------------
    def _answer_subquestion(self, question: str, sub_q: str, notes) -> str:
        system = (
            "You are a careful SQL analyst. Answer the given sub-question "
            "concretely against the provided schema."
        )
        prior = ""
        if notes:
            resolved = "\n\n".join(
                f"Sub-question {i}: {q}\nAnswer {i}: {a}"
                for i, (q, a) in enumerate(notes, 1)
            )
            prior = "Resolved so far:\n" + resolved + "\n\n"
        prompt = (
            "Database schema:\n" + self.schema + "\n\n"
            "Original question: " + question + "\n\n"
            + prior
            + "Current sub-question: " + sub_q + "\n\n"
            "Answer it briefly and concretely: name the exact tables and "
            "columns, the join keys, filter values, and aggregations, and "
            "give the SQL fragment that computes this step. "
            "Keep it under 120 words."
        )
        return (self.llm(prompt, system=system, temperature=0.0) or "").strip()

    # ------------------------------------------------------------------
    # Step 3: assembly
    # ------------------------------------------------------------------
    def _assemble(self, question: str, notes) -> str:
        system = (
            "You are an expert SQL generator. Produce exactly one SQL query."
        )
        trail = "\n".join(
            f"{i}. Q: {q}\n   A: {a}" for i, (q, a) in enumerate(notes, 1)
        )
        prompt = (
            "Database schema:\n" + self.schema + "\n\n"
            "Original question: " + question + "\n\n"
            "Sub-question analysis (in order):\n" + trail + "\n\n"
            "Using the analysis above, write ONE complete SQL query that "
            "answers the original question. Combine the sub-steps with "
            "joins, subqueries, CTEs, or set operations as needed. "
            "Return ONLY the SQL query, no explanation."
        )
        return self.llm(prompt, system=system, temperature=0.0)

    # ------------------------------------------------------------------
    # Step 4: single-shot repair on execution error
    # ------------------------------------------------------------------
    def _repair(self, question: str, notes, bad_sql: str, error: str) -> str:
        system = "You are an expert SQL debugger."
        prompt = (
            "Database schema:\n" + self.schema + "\n\n"
            "Question: " + question + "\n\n"
            "This SQL query failed:\n" + bad_sql + "\n\n"
            "Database error:\n" + str(error) + "\n\n"
            "Fix the query using only tables and columns present in the "
            "schema. Return ONLY the corrected SQL query, no explanation."
        )
        return self.llm(prompt, system=system, temperature=0.0)