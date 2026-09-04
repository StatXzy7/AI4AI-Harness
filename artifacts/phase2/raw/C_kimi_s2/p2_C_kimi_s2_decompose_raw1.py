"""Decompose the question into ordered sub-questions, answer each with its own small LLM call, then assemble, execute, and repair the final SQL."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2Decompose(SQLHarness):
    """Plan-and-solve Text-to-SQL harness.

    Control flow (implemented in code, not just in a prompt):
      1. DECOMPOSE: one LLM call breaks the question into an ordered
         numbered list of sub-questions.
      2. SOLVE: each sub-question is answered by its own small LLM call,
         conditioned on the schema, the original question, and all
         previously resolved sub-answers.
      3. ASSEMBLE: a final LLM call merges the sub-question/answer trace
         into one SQL query, which is extracted, executed, and repaired
         once if the database reports an error.
    """

    MAX_SUBQUESTIONS = 6

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------
    def solve(self, question: str) -> str:
        sub_questions = self._decompose(question)
        answers = self._answer_subquestions(question, sub_questions)
        sql = self._assemble(question, sub_questions, answers)
        if not sql:
            sql = self._direct_sql(question)
        sql = self._validate_and_repair(question, sql)
        return sql

    # ------------------------------------------------------------------
    # stage 1: decomposition
    # ------------------------------------------------------------------
    def _decompose(self, question: str) -> list:
        system = "You are a careful query planner for Text-to-SQL."
        prompt = (
            "Database schema:\n"
            + self.schema
            + "\n\nQuestion: "
            + question
            + "\n\nBreak this question into an ordered list of 2 to "
            + str(self.MAX_SUBQUESTIONS)
            + " concrete sub-questions that, when answered in order, lead to "
            "the final SQL query.\n"
            "Each sub-question should pin down needed tables/columns, literal "
            "values, filters, joins, aggregations, grouping, or ordering.\n"
            "Output ONLY a numbered list, one sub-question per line, e.g.:\n"
            "1. ...\n2. ...\n3. ...\n"
        )
        try:
            text = self.llm(prompt, system=system, temperature=0.0, n=1) or ""
        except Exception:
            return [question]
        subs = self._parse_numbered_list(text)
        if not subs:
            subs = [question]
        return subs[: self.MAX_SUBQUESTIONS]

    @staticmethod
    def _parse_numbered_list(text: str) -> list:
        items = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(?:\d+\s*[\.\):\-]?|[-*\u2022])\s*(.+)$", line)
            if m:
                item = m.group(1).strip()
                if item:
                    items.append(item)
        return items

    # ------------------------------------------------------------------
    # stage 2: answer each sub-question with a small LLM call
    # ------------------------------------------------------------------
    def _answer_subquestions(self, question: str, sub_questions: list) -> list:
        answers = []
        for i, sq in enumerate(sub_questions, 1):
            prior = ""
            if answers:
                lines = ["Sub-questions already resolved:"]
                for j, (q, a) in enumerate(zip(sub_questions, answers), 1):
                    lines.append(str(j) + ". " + q + "\n   Answer: " + a)
                prior = "\n".join(lines) + "\n\n"
            system = "You are a precise Text-to-SQL reasoning assistant."
            prompt = (
                "Database schema:\n"
                + self.schema
                + "\n\nOriginal question: "
                + question
                + "\n\n"
                + prior
                + "Sub-question "
                + str(i)
                + ": "
                + sq
                + "\n\nAnswer this sub-question concisely. Name the relevant "
                "tables/columns, literal values, filters, joins, or "
                "aggregations, and include a SQL fragment for this step if "
                "one applies.\nAnswer:"
            )
            try:
                ans = (self.llm(prompt, system=system, temperature=0.0, n=1) or "").strip()
            except Exception as exc:
                ans = "(unresolved: " + str(exc) + ")"
            if not ans:
                ans = "(no answer produced)"
            answers.append(ans)
        return answers

    # ------------------------------------------------------------------
    # stage 3: assemble the final SQL from the sub-question trace
    # ------------------------------------------------------------------
    def _assemble(self, question: str, sub_questions: list, answers: list) -> str:
        qa_lines = []
        for i, (q, a) in enumerate(zip(sub_questions, answers), 1):
            qa_lines.append(str(i) + ". " + q + "\n   Answer: " + a)
        qa_block = "\n".join(qa_lines)
        system = "You are an expert SQL generator. Output only SQL."
        prompt = (
            "Database schema:\n"
            + self.schema
            + "\n\nQuestion: "
            + question
            + "\n\nSub-question analysis:\n"
            + qa_block
            + "\n\nUsing the analysis above, write ONE SQL query that answers "
            "the original question. Combine the step fragments consistently "
            "and return ONLY the final SQL query, with no explanation.\nSQL:"
        )
        try:
            text = self.llm(prompt, system=system, temperature=0.0, n=1) or ""
        except Exception:
            return ""
        sql = bridge.extract_sql(text)
        if not sql:
            sql = text.strip()
        return sql

    # ------------------------------------------------------------------
    # fallback: direct single-shot generation
    # ------------------------------------------------------------------
    def _direct_sql(self, question: str) -> str:
        system = "You are an expert SQL generator. Output only SQL."
        prompt = (
            "Database schema:\n"
            + self.schema
            + "\n\nQuestion: "
            + question
            + "\n\nWrite ONE SQL query that answers the question. "
            "Return ONLY the SQL query.\nSQL:"
        )
        try:
            text = self.llm(prompt, system=system, temperature=0.0, n=1) or ""
        except Exception:
            return ""
        sql = bridge.extract_sql(text)
        if not sql:
            sql = text.strip()
        return sql

    # ------------------------------------------------------------------
    # stage 4: execute, and repair once on failure
    # ------------------------------------------------------------------
    def _validate_and_repair(self, question: str, sql: str) -> str:
        if not sql:
            return sql
        try:
            result = self.execute(sql)
        except Exception:
            return sql
        if result.get("ok"):
            return sql
        error = result.get("error", "unknown error")

        system = "You are an expert SQL debugger. Output only corrected SQL."
        prompt = (
            "Database schema:\n"
            + self.schema
            + "\n\nQuestion: "
            + question
            + "\n\nThe following SQL query failed:\n"
            + sql
            + "\n\nDatabase error: "
            + error
            + "\n\nFix the query so it runs correctly and still answers the "
            "question. Return ONLY the corrected SQL query.\nSQL:"
        )
        try:
            text = self.llm(prompt, system=system, temperature=0.0, n=1) or ""
        except Exception:
            return sql
        fixed = bridge.extract_sql(text)
        if not fixed:
            fixed = text.strip()
        if not fixed:
            return sql
        try:
            check = self.execute(fixed)
            if check.get("ok"):
                return fixed
        except Exception:
            pass
        # The original is known-bad; prefer the repaired candidate.
        return fixed