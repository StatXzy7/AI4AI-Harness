"""Decompose the question into ordered sub-questions, answer each one with its own small LLM call, then assemble the partial SQL answers into a single execution-validated SQLite query."""

import re
from typing import List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS1Decompose(SQLHarness):
    """Harness pipeline: plan -> per-step solve -> assemble -> validate/repair."""

    MAX_SUBS = 6      # cap on decomposition depth (bounds cost)
    MAX_REPAIRS = 2   # repair attempts when the assembled SQL fails to execute

    # ---------------------------------------------------------- plumbing

    def _schema_block(self) -> str:
        return (self.schema or "No schema provided.").strip()

    def _call(self, prompt: str, system: str = "") -> str:
        """One deterministic LLM call, hardened against odd return shapes."""
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if out is None:
            return ""
        return str(out).strip()

    def _sql_from(self, text: str) -> str:
        """Extract a clean SQL string from an LLM reply."""
        try:
            sql = bridge.extract_sql(text or "")
        except Exception:
            sql = text or ""
        sql = (sql or "").strip()
        while sql.endswith(";"):
            sql = sql[:-1].strip()
        return sql

    def _run(self, sql: str) -> Optional[dict]:
        try:
            return self.execute(sql)
        except Exception:
            return None

    def _ok(self, sql: str) -> bool:
        res = self._run(sql)
        return bool(res and res.get("ok"))

    # ---------------------------------------------------- Stage 1: plan

    _PLAN_SYS = (
        "You are a query planner for relational databases. You break a question "
        "into the minimal ordered list of simpler sub-questions, each answerable "
        "by one small SQL query."
    )

    def _decompose(self, question: str) -> List[str]:
        prompt = (
            "Database schema:\n" + self._schema_block() + "\n\n"
            "Question: " + question + "\n\n"
            "Task: decompose this question into 1-" + str(self.MAX_SUBS) +
            " ordered sub-questions, in the order they must be answered "
            "(later steps may depend on earlier ones).\n"
            "Rules:\n"
            "- Output ONLY numbered lines: '1. <sub-question>'\n"
            "- One sub-question per line. No SQL. No explanations. No extra text.\n"
            "- If the question is already simple, output it as the single line.\n"
        )
        text = self._call(prompt, self._PLAN_SYS)

        subs: List[str] = []
        for line in text.splitlines():
            line_s = line.strip().lstrip("*-\u2022").strip()
            m = re.match(r"^\d+\s*[.)\]:-]\s*(.+?)\s*$", line_s)
            if m:
                subs.append(m.group(1).strip().strip("*").strip())

        # Tolerate unnumbered, one-question-per-line output.
        if not subs:
            plain = [ln.strip().lstrip("*-\u2022").strip() for ln in text.splitlines() if ln.strip()]
            if 2 <= len(plain) <= self.MAX_SUBS and all(ln.endswith("?") for ln in plain):
                subs = plain

        # Drop SQL-looking, oversized, or duplicated entries.
        seen = set()
        cleaned: List[str] = []
        for s in subs:
            if not s or len(s) > 400:
                continue
            if re.search(r"\bselect\b[\s\S]+\bfrom\b", s, re.IGNORECASE):
                continue
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(s)

        if not cleaned:
            cleaned = [question]
        return cleaned[: self.MAX_SUBS]

    # -------------------------------------------------- Stage 2: per-step solve

    _SOLVE_SYS = (
        "You are an expert SQLite query writer. You answer exactly one "
        "sub-question with one small, self-contained SELECT query."
    )

    def _answer_sub(self, question: str, sub: str, idx: int,
                    prior: List[Tuple[str, str]]) -> str:
        ctx = ""
        if prior:
            ctx = ("Earlier steps already answered "
                   "(reuse their SQL as subqueries/CTEs if useful):\n")
            for j, (psub, psql) in enumerate(prior, 1):
                ctx += "\nStep " + str(j) + ": " + psub + "\nSQL:\n" + psql + "\n"
            ctx += "\n"

        prompt = (
            "Database schema:\n" + self._schema_block() + "\n\n"
            "Overall question (context only, do NOT answer it): " + question + "\n\n"
            + ctx +
            "Your sub-question (step " + str(idx) + " of the plan): " + sub + "\n\n"
            "Write ONE small SQLite SELECT query that answers ONLY this sub-question.\n"
            "Output the SQL in a