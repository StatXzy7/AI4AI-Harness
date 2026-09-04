"""Decompose the question into ordered sub-questions, answer each with a small LLM call grounded by executed SQL fragments, then assemble and execution-validate the final SQL."""

from __future__ import annotations

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS1Decompose(SQLHarness):
    """Plan-then-solve Text-to-SQL harness.

    Control flow:
      1. DECOMPOSE -- one LLM call breaks the question into ordered sub-questions.
      2. SOLVE     -- each sub-question is answered by a small LLM call; any SQL
                      fragment it proposes is executed and the observed rows are
                      appended to the step record as grounding evidence.
      3. ASSEMBLE  -- one LLM call merges the question plus all step records into
                      a single final SQL query.
      4. VALIDATE  -- the final SQL is executed; on failure a bounded repair loop
                      feeds the database error back to the LLM.
    """

    MAX_SUBQUESTIONS = 6
    MAX_EVIDENCE_ROWS = 8
    MAX_REPAIR_ATTEMPTS = 2

    # ------------------------------------------------------------------ #
    # entry point                                                        #
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        # 1. Decompose the question into ordered sub-questions.
        subquestions = self._decompose(question)
        if not subquestions:
            subquestions = [question]
        subquestions = subquestions[: self.MAX_SUBQUESTIONS]

        # 2. Answer each sub-question in order, threading prior steps forward.
        steps = []
        for idx, subq in enumerate(subquestions, start=1):
            steps.append(self._solve_subquestion(question, idx, subq, steps))

        # 3. Assemble the final SQL from the solved steps.
        final_sql = self._assemble(question, steps)
        if not final_sql:
            final_sql = self._direct_fallback(question)

        # 4. Execution validation with a bounded repair loop.
        result = self._run_sql(final_sql)
        for _ in range(self.MAX_REPAIR_ATTEMPTS):
            if result.get("ok"):
                break
            repaired = self._repair(question, steps, final_sql, result.get("error", ""))
            if not repaired or repaired == final_sql:
                break
            final_sql = repaired
            result = self._run_sql(final_sql)

        return final_sql

    # ------------------------------------------------------------------ #
    # stage 1: decomposition                                             #
    # ------------------------------------------------------------------ #

    def _decompose(self, question: str) -> list:
        system = (
            "You are a careful query planner for a Text-to-SQL system. "
            "You decompose complex questions into simple ordered steps."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Break this question into a small number of ordered sub-questions "
            "that, answered in order, produce the final answer. Each sub-question "
            "must be answerable with one simple SQL query or a short reasoning "
            "step over the schema. If the question is already simple, output a "
            "single sub-question.\n"
            "Output ONLY a numbered list, one sub-question per line:\n"
            "1. ...\n2. ..."
        )
        text = self._chat(prompt, system=system)
        return self._parse_numbered_list(text)

    # ------------------------------------------------------------------ #
    # stage 2: per-sub-question solving                                  #
    # ------------------------------------------------------------------ #

    def _solve_subquestion(self, question: str, idx: int, subq: str, prior_steps: list) -> dict:
        system = "You are a precise SQL analyst answering one step of a larger plan."
        history = self._format_steps(prior_steps) if prior_steps else "(none yet)"
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Original question: {question}\n\n"
            f"Plan so far:\n{history}\n\n"
            f"Current step {idx}: {subq}\n\n"
            "Answer this step. If it needs data from the database, provide one "
            "SQL query that retrieves exactly the needed values.\n"
            "Respond in EXACTLY this format:\n"
            "ANSWER: <one short sentence>\n"
            "SQL: <one SQL query, or NONE if no query is needed>"
        )
        text = self._chat(prompt, system=system)
        answer, sql = self._parse_answer_block(text)

        record = {"q": subq, "answer": answer or text, "sql": sql, "evidence": ""}
        if sql:
            res = self._run_sql(sql)
            if res.get("ok"):
                record["evidence"] = self._format_rows(res.get("rows") or [])
            else:
                record["evidence"] = f"SQL error: {res.get('error', 'unknown error')}"
        return record

    # ------------------------------------------------------------------ #
    # stage 3: assembly                                                  #
    # ------------------------------------------------------------------ #

    def _assemble(self, question: str, steps: list) -> str:
        system = (
            "You are an expert SQL query writer. Combine step-by-step findings "
            "into one correct final SQL query."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Solved steps:\n{self._format_steps(steps)}\n\n"
            "Using the solved steps above, write ONE final SQL query that answers "
            "the original question. The query must be directly executable against "
            "the schema. Output ONLY the SQL query, no explanation."
        )
        text = self._chat(prompt, system=system)
        return self._extract_sql(text)

    # ------------------------------------------------------------------ #
    # stage 4: validation / repair                                       #
    # ------------------------------------------------------------------ #

    def _repair(self, question: str, steps: list, bad_sql: str, error: str) -> str:
        system = "You are an expert SQL debugger."
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Solved steps:\n{self._format_steps(steps)}\n\n"
            f"The following SQL query failed:\n{bad_sql}\n\n"
            f"Database error:\n{error}\n\n"
            "Fix the query so it runs correctly and still answers the question. "
            "Output ONLY the corrected SQL query."
        )
        text = self._chat(prompt, system=system)
        return self._extract_sql(text)

    def _direct_fallback(self, question: str) -> str:
        system = "You are an expert Text-to-SQL system."
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write ONE SQL query that answers the question. Output ONLY the SQL."
        )
        return self._extract_sql(self._chat(prompt, system=system))

    # ------------------------------------------------------------------ #
    # helpers                                                            #
    # ------------------------------------------------------------------ #

    def _chat(self, prompt: str, system: str = "") -> str:
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return str(out).strip()

    def _run_sql(self, sql: str) -> dict:
        try:
            return self.execute(sql)
        except Exception as exc:  # never let an engine exception crash the harness
            return {"ok": False, "rows": [], "error": str(exc)}

    @staticmethod
    def _parse_numbered_list(text: str) -> list:
        items = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(?:\d+[\.\):\-]\s*|[-*]\s+)(.+)$", line)
            if m:
                items.append(m.group(1).strip())
        return items

    @staticmethod
    def _parse_answer_block(text: str):
        answer, sql = "", ""
        m_ans = re.search(r"ANSWER\s*:\s*(.*?)(?=\n\s*SQL\s*:|\Z)", text, re.I | re.S)
        if m_ans:
            answer = m_ans.group(1).strip()
        m_sql = re.search(r"SQL\s*:\s*(.*)$", text, re.I | re.S)
        if m_sql:
            raw = m_sql.group(1).strip()
            if raw and not re.match(r"(?i)^(none|n/?a|no query)\b", raw):
                sql = bridge.extract_sql(raw) or raw.strip("` \n")
        return answer, sql

    @staticmethod
    def _extract_sql(text: str) -> str:
        sql = bridge.extract_sql(text)
        if sql:
            return sql.strip()
        return re.sub(r"