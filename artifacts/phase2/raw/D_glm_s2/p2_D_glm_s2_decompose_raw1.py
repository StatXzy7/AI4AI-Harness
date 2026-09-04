"""Decomposition harness: the question is split into an ordered list of sub-questions, each sub-question is answered by its own small LLM call, and the validated step results are then assembled into one final SQL query."""

import re

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2Decompose"]


class P2P2DGlmS2Decompose(SQLHarness):
    """Plan -> solve each step -> assemble -> execute-validate, with graceful fallbacks.

    Control flow (not just prompting) implements the strategy:
      1. _plan()         : one LLM call produces an ordered list of sub-questions.
      2. _answer_step()  : one *small* LLM call per sub-question -> step SQL,
                           each validated (and repaired) against the DB.
      3. _assemble()     : one LLM call merges the step SQL into the final query.
      4. candidates      : assembled SQL, last-step SQL, a deterministic CTE
                           stitch, and a single-shot fallback are tried in order;
                           the first one that executes cleanly is returned.
    """

    MAX_STEPS = 6         # cap on planned sub-questions
    MIN_STEPS = 2         # fewer than this -> decomposition is pointless
    STEP_FIX_TRIES = 1    # repair attempts per sub-question
    FINAL_FIX_TRIES = 2   # repair attempts for the assembled query

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # --- stage 1: plan the decomposition ---------------------------- #
        try:
            plan = self._plan(question)
        except Exception:
            plan = []

        if len(plan) < self.MIN_STEPS:
            return self._direct(question)

        # --- stage 2: answer each sub-question with a small LLM call ---- #
        solved = []
        for i in range(len(plan)):
            try:
                solved.append(self._answer_step(question, plan, i, solved))
            except Exception:
                solved.append("")

        # --- stage 3: assemble, stage 4: validate with fallbacks --------- #
        candidates = []
        try:
            candidates.append(self._assemble(question, plan, solved))
        except Exception:
            pass
        if solved and solved[-1]:
            candidates.append(solved[-1])              # last step often IS the answer
        try:
            candidates.append(self._stitch(solved))    # deterministic CTE chain
        except Exception:
            pass
        candidates.append(self._direct(question))      # single-shot fallback

        for sql in candidates:
            if self._works(sql):
                return sql
        return next((c for c in candidates if c), "")

    # ------------------------------------------------------------------ #
    # stage 1: decomposition planning
    # ------------------------------------------------------------------ #
    def _plan(self, question: str) -> list:
        system = (
            "You are a query planner. Split the question into numbered "
            "sub-questions only -- never write SQL."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Break the question into the shortest ordered list of simple sub-questions "
            "that, answered one by one, fully resolve it.\n"
            "Rules:\n"
            "- Between 2 and 5 sub-questions.\n"
            "- Each sub-question must be answerable by one small SQL query on the schema.\n"
            "- Order them so later steps can reuse earlier results.\n"
            "- The last sub-question is the original question itself.\n"
            "Output ONLY the numbered list, one sub-question per line:\n"
            "1. ...\n2. ..."
        )
        text = self._call(prompt, system)

        steps, seen = [], set()
        for line in text.splitlines():
            m = re.match(
                r"^\s*(?:(?:\d{1,2}|step\s*\d{1,2})\s*[.):\]-]|[-*])\s*(\S.*)$",
                line,
                re.IGNORECASE,
            )
            if not m:
                continue
            step = m.group(1).strip()
            key = step.lower()
            if len(step) >= 3 and key not in seen:
                seen.add(key)
                steps.append(step)
        return steps[: self.MAX_STEPS]

    # ------------------------------------------------------------------ #
    # stage 2: small, focused LLM call for a single sub-question
    # ------------------------------------------------------------------ #
    def _answer_step(self, question: str, plan: list, i: int, solved: list) -> str:
        system = (
            "You are an expert SQLite writer. Reply with ONE small SQL query "
            "and nothing else."
        )
        context = ""
        for j, sql in enumerate(solved):
            context += f"Step {j + 1} ({plan[j]}) was answered by:\n{sql or '(no SQL)'}\n\n"
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Original question: {question}\n\n"
            f"Full plan:\n{self._fmt_plan(plan)}\n\n"
            + (f"Already-computed steps:\n{context}" if context else "")
            + f"Write SQLite SQL that answers ONLY step {i + 1}: {plan[i]}\n"
            "Keep the query small and focused on this single step. "
            "Output the SQL query only."
        )
        sql = self._sql_of(self._call(prompt, system))
        ok, err = self._run(sql)
        if ok:
            return sql
        for _ in range(self.STEP_FIX_TRIES):
            fix = (
                f"{prompt}\n\nYour previous SQL was:\n{sql or '(none)'}\n"
                f"It failed with error: {err}\n"
                "Output one corrected SQL query only."
            )
            cand = self._sql_of(self._call(fix, system, temperature=0.2))
            ok, err = self._run(cand)
            if ok:
                return cand
            if cand:
                sql = cand
        return sql  # keep best effort; the assembler can still use it as context

    # ------------------------------------------------------------------ #
    # stage 3: assemble the step solutions into the final query
    # ------------------------------------------------------------------ #
    def _assemble(self, question: str, plan: list, solved: list) -> str:
        system = (
            "You are an expert SQLite writer. Merge partial step solutions into "
            "ONE final query. Output the SQL query only."
        )
        parts = ""
        for j, (sub, sql) in enumerate(zip(plan, solved)):
            parts += f"\nStep {j + 1} - {sub}\nSQL:\n{sql or '(no SQL produced)'}\n"
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Original question: {question}\n\n"
            f"Step-by-step solutions:{parts}\n"
            "Combine these steps into ONE final SQLite query that answers the original "
            "question, reusing the step SQL (as CTEs or subqueries) wherever useful.\n"
            "Output the SQL query only."
        )
        sql = self._sql_of(self._call(prompt, system))
        ok, err = self._run(sql)
        if ok:
            return sql
        for _ in range(self.FINAL_FIX_TRIES):
            fix = (
                f"{prompt}\n\nYour previous final SQL was:\n{sql or '(none)'}\n"
                f"It failed with error: {err}\n"
                "Output one corrected final SQL query only."
            )
            cand = self._sql_of(self._call(fix, system, temperature=0.2))
            ok, err = self._run(cand)
            if ok:
                return cand
            if cand:
                sql = cand
        return sql

    # ------------------------------------------------------------------ #
    # deterministic fallback: chain every step SQL as CTEs
    # ------------------------------------------------------------------ #
    def _stitch(self, solved: list) -> str:
        ctes, last = [], None
        for j, sql in enumerate(solved):
            if not sql:
                continue
            body = sql.strip().rstrip(";").strip()
            ctes.append(f"step{j + 1} AS (\n{body}\n)")
            last = f"step{j + 1}"
        if last is None:
            return ""
        return "WITH " + ",\n".join(ctes) + f"\nSELECT * FROM {last}"

    # ------------------------------------------------------------------ #
    # single-shot fallback (also used when planning yields < MIN_STEPS)
    # ------------------------------------------------------------------ #
    def _direct(self, question: str) -> str:
        system = (
            "You are an expert text-to-SQL system for SQLite. "
            "Output one SQL query only."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite query that answers the question. "
            "Output the SQL query only."
        )
        try:
            return self._sql_of(self._call(prompt, system))
        except Exception:
            return ""

    # ------------------------------------------------------------------ #
    # small utilities
    # ------------------------------------------------------------------ #
    def _call(self, prompt: str, system: str, temperature: float = 0.0) -> str:
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if not isinstance(out, str):
            out = "" if out is None else str(out)
        return out.strip()

    def _sql_of(self, text: str) -> str:
        try:
            return (bridge.extract_sql(text) or "").strip()
        except Exception:
            return ""

    def _run(self, sql: str):
        """Execute defensively; return (ok, error)."""
        if not self._safe(sql):
            return False, "empty or non-SELECT SQL"
        try:
            res = self.execute(sql)
        except Exception as e:  # the frozen executor itself blew up
            return False, str(e)
        if isinstance(res, dict) and res.get("ok"):
            return True, ""
        err = str(res.get("error") or "") if isinstance(res, dict) else ""
        return False, err or "execution failed"

    def _works(self, sql: str) -> bool:
        return self._run(sql)[0]

    def _safe(self, sql: str) -> bool:
        s = (sql or "").strip()
        if not s:
            return False
        if not re.match(r"(?is)\A\s*(select|with)\b", s):
            return False
        if ";" in s.rstrip(";"):  # reject multi-statement payloads
            return False
        return True

    @staticmethod
    def _fmt_plan(plan: list) -> str:
        return "\n".join(f"{i + 1}. {s}" for i, s in enumerate(plan))