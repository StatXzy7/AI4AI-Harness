"""Decompose the question into ordered sub-questions, answer each with a small focused LLM call, then assemble and execution-verify the final SQL."""

import re
from typing import List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1Decompose(SQLHarness):
    """Decompose-and-assemble Text-to-SQL harness wrapping a frozen weak solver.

    Control flow:
      1. Decompose the natural-language question into an ordered list of
         atomic sub-questions (one LLM call).
      2. Answer each sub-question with its own small LLM call, conditioning on
         the schema and on the answers to all previous sub-questions.
      3. Assemble the collected sub-question/answer trace into the final SQL
         query (one LLM call).
      4. Execution-verify the SQL and repair it with focused LLM calls while
         the database keeps reporting errors.
    """

    MAX_SUBQUESTIONS = 6
    MAX_REPAIR_ROUNDS = 2

    PLAN_SYSTEM = (
        "You are a meticulous query planner for a SQLite Text-to-SQL system."
    )
    SOLVER_SYSTEM = (
        "You are a SQLite expert who answers sub-questions precisely and concisely."
    )
    SQL_SYSTEM = (
        "You are a SQLite expert who outputs exactly one valid SQL query and nothing else."
    )

    # ------------------------------------------------------------------ API
    def solve(self, question: str) -> str:
        # Step 1: ordered decomposition.
        sub_questions = self._decompose(question)
        # Step 2: answer each sub-question with a small dedicated LLM call.
        qa_pairs = self._answer_sub_questions(question, sub_questions)
        # Step 3: assemble the final SQL from the sub-question/answer trace.
        sql = self._assemble(question, qa_pairs)
        if not sql:
            sql = self._direct_sql(question, qa_pairs)
        if not sql:
            sql = "SELECT 1"
        # Step 4: verify against the database and repair if necessary.
        return self._verify_and_repair(question, sql, qa_pairs)

    # ------------------------------------------------------- LLM convenience
    def _ask(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        """Single small LLM call; always returns a stripped string."""
        try:
            out = self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return str(out).strip()

    # ------------------------------------------------------- Step 1: decompose
    def _decompose(self, question: str) -> List[str]:
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Decompose this question into an ordered list of at most "
            f"{self.MAX_SUBQUESTIONS} atomic sub-questions that, when answered in "
            "order, fully determine how to write the final SQL query (which tables "
            "and columns to use, which literal values and filters apply, how to "
            "join, aggregate, order and limit).\n"
            "Rules:\n"
            "- Each sub-question must be answerable from the schema and question.\n"
            "- Keep the order dependency-safe: later sub-questions may rely on "
            "earlier answers.\n"
            "- Output ONLY the numbered list, one sub-question per line, e.g. "
            '"1. ...".'
        )
        text = self._ask(prompt, system=self.PLAN_SYSTEM)
        sub_questions = self._parse_numbered_list(text)
        if not sub_questions:
            # Fallback: treat the whole question as a single sub-question.
            sub_questions = [question]
        return sub_questions[: self.MAX_SUBQUESTIONS]

    @staticmethod
    def _parse_numbered_list(text: str) -> List[str]:
        items: List[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^(?:\d+\s*[\.\):]|[-*\u2022])\s*(.+)$", line)
            if match:
                item = match.group(1).strip().strip('"').strip()
                if item:
                    items.append(item)
        return items

    # --------------------------------------------- Step 2: answer sub-questions
    def _answer_sub_questions(
        self, question: str, sub_questions: List[str]
    ) -> List[Tuple[str, str]]:
        qa_pairs: List[Tuple[str, str]] = []
        for index, sub_question in enumerate(sub_questions, start=1):
            history = self._format_plan(qa_pairs) or "(none yet)"
            prompt = (
                "Database schema:\n"
                f"{self.schema}\n\n"
                f"Original question: {question}\n\n"
                f"Previously resolved sub-questions:\n{history}\n\n"
                f"Sub-question {index}: {sub_question}\n\n"
                "Answer this sub-question concisely and concretely: name the exact "
                "tables, columns, literal values, join keys, filter conditions, "
                "aggregations, ordering, limit, or SQL fragment it implies. Reuse "
                "earlier answers whenever the sub-question depends on them."
            )
            answer = self._ask(prompt, system=self.SOLVER_SYSTEM)
            qa_pairs.append((sub_question, answer))
        return qa_pairs

    # -------------------------------------------------------- Step 3: assemble
    def _assemble(self, question: str, qa_pairs: List[Tuple[str, str]]) -> str:
        plan = self._format_plan(qa_pairs)
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Step-by-step analysis of the question:\n"
            f"{plan}\n\n"
            "Using ONLY the analysis above, write ONE SQLite query that answers the "
            "question exactly.\n"
            "Requirements:\n"
            "- Use only tables and columns that exist in the schema.\n"
            "- Apply every filter, join, aggregation, ordering and limit identified "
            "in the analysis.\n"
            "- Return ONLY the SQL query (no markdown fences, no explanation)."
        )
        text = self._ask(prompt, system=self.SQL_SYSTEM)
        return bridge.extract_sql(text)

    def _direct_sql(self, question: str, qa_pairs: List[Tuple[str, str]]) -> str:
        """Fallback one-shot generation if assembly extraction came back empty."""
        plan = self._format_plan(qa_pairs)
        plan_block = f"\nAnalysis of the question:\n{plan}\n" if plan else ""
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n"
            f"{plan_block}\n"
            f"Question: {question}\n\n"
            "Write ONE SQLite query that answers the question. Return ONLY the SQL."
        )
        text = self._ask(prompt, system=self.SQL_SYSTEM)
        return bridge.extract_sql(text) or text

    # ------------------------------------------------ Step 4: verify & repair
    def _verify_and_repair(
        self, question: str, sql: str, qa_pairs: List[Tuple[str, str]]
    ) -> str:
        current = sql
        for _ in range(self.MAX_REPAIR_ROUNDS + 1):
            try:
                result = self.execute(current)
            except Exception as exc:  # defensive: treat harness errors as DB errors
                result = {"ok": False, "rows": [], "error": str(exc)}
            if result.get("ok"):
                return current
            error = str(result.get("error", "unknown error"))
            fixed = self._repair(question, current, error, qa_pairs)
            if not fixed or fixed == current:
                break
            current = fixed
        return current

    def _repair(
        self, question: str, sql: str, error: str, qa_pairs: List[Tuple[str, str]]
    ) -> str:
        plan = self._format_plan(qa_pairs)
        plan_block = f"\nAnalysis of the question:\n{plan}\n" if plan else ""
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n"
            f"{plan_block}\n"
            f"Question: {question}\n\n"
            f"The following SQL query failed:\n{sql}\n\n"
            f"SQLite error message:\n{error}\n\n"
            "Fix the query so it runs on this schema and still answers the question "
            "according to the analysis. Return ONLY the corrected SQL query."
        )
        text = self._ask(prompt, system=self.SQL_SYSTEM)
        return bridge.extract_sql(text)

    # --------------------------------------------------------------- utilities
    @staticmethod
    def _format_plan(qa_pairs: List[Tuple[str, str]]) -> str:
        return "\n".join(
            f"{i}. Q: {q}\n   A: {a}" for i, (q, a) in enumerate(qa_pairs, start=1)
        )