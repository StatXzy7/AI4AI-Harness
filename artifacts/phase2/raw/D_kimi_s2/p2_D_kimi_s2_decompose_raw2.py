"""Decompose the question into ordered sub-questions, answer each with its own small LLM call over the schema plus accumulated findings, then assemble the final SQL from all sub-answers."""

import re
from typing import List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2Decompose(SQLHarness):
    """Text-to-SQL via explicit, control-flow question decomposition.

    Pipeline (implemented in control flow, not only in prompts):
      1. DECOMPOSE -- one LLM call splits the question into an ordered
         list of sub-questions; the list is parsed here in Python.
      2. SOLVE -- a loop issues one small LLM call per sub-question; every
         call sees the schema, the original question, and all previous
         (sub-question, answer) pairs, so later steps build on earlier ones.
      3. ASSEMBLE -- a final LLM call merges every finding into one SQL
         query, extracted with ``bridge.extract_sql``.
      4. VALIDATE -- the SQL is executed; on database error a single
         repair call is made and the fixed query is re-executed.
    """

    MAX_SUBQUESTIONS = 8
    MAX_REPAIRS = 1

    SYS_DECOMPOSE = (
        "You are a query planner for a text-to-SQL engine. You break a "
        "complex question into simple, ordered sub-questions."
    )
    SYS_SOLVE = (
        "You are a meticulous SQL analyst. You resolve one sub-question at "
        "a time using the schema and previously established findings."
    )
    SYS_ASSEMBLE = (
        "You are an expert SQLite engineer. You combine partial findings "
        "into one correct, executable SQL query."
    )
    SYS_REPAIR = "You are an expert SQLite debugger. You fix broken SQL queries."

    # ------------------------------------------------------------------ #
    # entry point                                                         #
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        # 1) Decompose into ordered sub-questions (real control flow).
        subquestions = self._decompose(question)

        # 2) One small LLM call per sub-question, threading findings forward.
        findings: List[Tuple[str, str]] = []
        for idx, subq in enumerate(subquestions, start=1):
            answer = self._answer_subquestion(question, subq, idx, findings)
            findings.append((subq, answer))

        # 3) Assemble the final SQL from all sub-answers.
        sql = self._assemble(question, findings)

        # 4) Execute; repair once if the database rejects the query.
        sql = self._validate_and_repair(question, sql)

        # Last resort: plain single-shot generation if nothing survived.
        if not sql:
            sql = self._direct_fallback(question)
        return sql

    # ------------------------------------------------------------------ #
    # step 1: decomposition                                               #
    # ------------------------------------------------------------------ #

    def _decompose(self, question: str) -> List[str]:
        prompt = (
            "Database schema:\n{schema}\n\n"
            "Question: {question}\n\n"
            "Break the question into an ordered list of at most {k} simple "
            "sub-questions that, answered in order, yield everything needed "
            "to write the final SQL query (which tables/columns to use, "
            "which filters, joins, aggregates, ordering, limits). Each "
            "sub-question must be self-contained and answerable from the "
            "schema.\n"
            "Output ONLY the numbered list, one item per line, e.g.:\n"
            "1. ...\n2. ..."
        ).format(schema=self.schema, question=question, k=self.MAX_SUBQUESTIONS)
        raw = self.llm(prompt, system=self.SYS_DECOMPOSE, temperature=0.0)
        subquestions = self._parse_subquestions(raw)
        if not subquestions:  # decomposition failed -> atomic fallback
            subquestions = [question]
        return subquestions[: self.MAX_SUBQUESTIONS]

    @staticmethod
    def _parse_subquestions(text: str) -> List[str]:
        items: List[str] = []
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(
                r"^(?:sub-?question\s*|step\s*|q\s*)?\d+\s*[\.\)\:\-]\s*(.+?)\s*$",
                line,
                re.IGNORECASE,
            )
            if m:
                items.append(m.group(1))
            elif line.startswith(("-", "*")) and len(line) > 2:
                items.append(line.lstrip("-* ").strip())
        return items

    # ------------------------------------------------------------------ #
    # step 2: per-sub-question solving                                    #
    # ------------------------------------------------------------------ #

    def _answer_subquestion(
        self,
        question: str,
        subq: str,
        idx: int,
        findings: List[Tuple[str, str]],
    ) -> str:
        if findings:
            history = "Findings established so far:\n" + "\n".join(
                "{j}. {q}\n   -> {a}".format(j=j, q=q, a=a)
                for j, (q, a) in enumerate(findings, start=1)
            ) + "\n\n"
        else:
            history = ""
        prompt = (
            "Database schema:\n{schema}\n\n"
            "Original question: {question}\n\n"
            "{history}"
            "Sub-question {idx}: {subq}\n\n"
            "Resolve ONLY this sub-question. State the concrete tables, "
            "columns, values, joins, filters or aggregates involved, and "
            "include a SQL fragment when useful. Be brief (<= 80 words)."
        ).format(
            schema=self.schema,
            question=question,
            history=history,
            idx=idx,
            subq=subq,
        )
        return self.llm(prompt, system=self.SYS_SOLVE, temperature=0.0).strip()

    # ------------------------------------------------------------------ #
    # step 3: assembly                                                    #
    # ------------------------------------------------------------------ #

    def _assemble(self, question: str, findings: List[Tuple[str, str]]) -> str:
        steps = "\n".join(
            "Step {j}: {q}\nFinding {j}: {a}".format(j=j, q=q, a=a)
            for j, (q, a) in enumerate(findings, start=1)
        )
        prompt = (
            "Database schema:\n{schema}\n\n"
            "Question: {question}\n\n"
            "The question was decomposed and each step resolved:\n"
            "{steps}\n\n"
            "Assemble these findings into ONE SQLite query that answers the "
            "question exactly. Output only the SQL query."
        ).format(schema=self.schema, question=question, steps=steps)
        raw = self.llm(prompt, system=self.SYS_ASSEMBLE, temperature=0.0)
        return bridge.extract_sql(raw).strip() or raw.strip()

    # ------------------------------------------------------------------ #
    # step 4: validation + repair                                         #
    # ------------------------------------------------------------------ #

    def _validate_and_repair(self, question: str, sql: str) -> str:
        for attempt in range(self.MAX_REPAIRS + 1):
            if not sql:
                break
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            if attempt < self.MAX_REPAIRS:
                sql = self._repair(question, sql, result.get("error", ""))
        return sql

    def _repair(self, question: str, sql: str, error: str) -> str:
        prompt = (
            "Database schema:\n{schema}\n\n"
            "Question: {question}\n\n"
            "The following SQL query failed:\n{sql}\n\n"
            "Database error: {error}\n\n"
            "Fix the query so it executes correctly and answers the "
            "question. Output only the corrected SQL query."
        ).format(schema=self.schema, question=question, sql=sql, error=error)
        raw = self.llm(prompt, system=self.SYS_REPAIR, temperature=0.0)
        return bridge.extract_sql(raw).strip() or raw.strip()

    # ------------------------------------------------------------------ #
    # fallback                                                            #
    # ------------------------------------------------------------------ #

    def _direct_fallback(self, question: str) -> str:
        prompt = (
            "Database schema:\n{schema}\n\n"
            "Question: {question}\n\n"
            "Write one SQLite query that answers the question. "
            "Output only the SQL query."
        ).format(schema=self.schema, question=question)
        raw = self.llm(prompt, system=self.SYS_ASSEMBLE, temperature=0.0)
        return bridge.extract_sql(raw).strip() or raw.strip()