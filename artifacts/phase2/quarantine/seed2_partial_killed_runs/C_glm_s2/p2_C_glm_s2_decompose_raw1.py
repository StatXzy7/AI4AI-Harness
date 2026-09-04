"""Decomposes the input question into an ordered plan of sub-questions, answers each with its own small LLM SQL call (executed for evidence), then assembles and execution-repairs the final SQL query."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS2Decompose(SQLHarness):
    """Plan-and-solve harness: decompose -> per-sub-question SQL -> assemble -> repair."""

    MAX_SUBQUESTIONS = 5   # hard cap on decomposition steps
    SUB_REPAIRS = 1        # repair attempts allowed per sub-question fragment
    FINAL_REPAIRS = 3      # repair attempts allowed for assembled / fallback SQL
    PREVIEW_ROWS = 5       # rows shown to later stages as execution evidence
    PREVIEW_CHARS = 400    # truncation for result previews

    SQL_SYSTEM = "You are an expert SQLite programmer. Output exactly one valid SQL query and nothing else."
    PLAN_SYSTEM = "You are a precise query planner. Follow the requested output format exactly."

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return "SELECT 1"

        best = "SELECT 1"
        try:
            # ---- Stage 1: decompose the question into an ordered plan ----
            subquestions = self._decompose(question)
            if not subquestions:
                subquestions = [question]
            subquestions = subquestions[: self.MAX_SUBQUESTIONS]

            # ---- Stage 2: answer each sub-question with its own LLM call ----
            steps = []
            for idx, subq in enumerate(subquestions, start=1):
                sql = self._answer_subquestion(question, subq, steps)
                if sql:
                    best = sql

                # goal string tells the repairer what this particular SQL must do
                goal = f"{question} -- (step {idx}/{len(subquestions)}: {subq})"
                sql, ok, res = self._run_with_repairs(
                    goal, sql, max_repairs=self.SUB_REPAIRS
                )
                if sql:
                    best = sql

                if sql:
                    result_line = self._preview(res)
                else:
                    result_line = "(no SQL produced for this step)"

                steps.append(
                    {
                        "index": idx,
                        "subquestion": subq,
                        "sql": sql or "(none)",
                        "result": result_line,
                        "ok": ok,
                    }
                )

            # ---- Stage 3: assemble the fragments into the final SQL ----
            final_sql = self._assemble(question, steps)
            if final_sql:
                best = final_sql
            final_sql, ok, _ = self._run_with_repairs(
                question, final_sql, steps=steps, max_repairs=self.FINAL_REPAIRS
            )
            if final_sql:
                best = final_sql
            if ok:
                return final_sql

            # ---- Fallback: single-shot generation, repaired the same way ----
            direct_sql = self._direct(question)
            if direct_sql:
                best = direct_sql
            direct_sql, ok2, _ = self._run_with_repairs(
                question, direct_sql, steps=steps, max_repairs=self.FINAL_REPAIRS
            )
            if direct_sql:
                best = direct_sql
            if ok2:
                return direct_sql

        except Exception:
            # Never crash the frozen eval: fall back to the best candidate so far.
            pass
        return best

    # ------------------------------------------------------------------ #
    # Stage 1: decomposition
    # ------------------------------------------------------------------ #

    def _decompose(self, question: str) -> list:
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Decompose this question into an ordered plan of 2 to "
            f"{self.MAX_SUBQUESTIONS} sub-questions. Rules:\n"
            "- Each sub-question must be answerable by a single SQL query against the schema above.\n"
            "- Each sub-question must be self-contained: mention the tables, columns, filters, or orderings it needs.\n"
            "- Later sub-questions may depend on the results of earlier ones.\n"
            "- Do not write SQL; write plain sub-questions only.\n"
            "Output ONLY the numbered list, one sub-question per line, exactly like:\n"
            "1. <first sub-question>\n"
            "2. <second sub-question>\n"
        )
        text = self._call(prompt, system=self.PLAN_SYSTEM)

        subs = []
        for raw in text.splitlines():
            line = raw.strip().strip("*").strip()
            if not line:
                continue
            m = re.match(r"^(?:\d+\s*[.)\]]|[-*\u2022])\s*(.+)$", line)
            if m:
                subs.append(m.group(1).strip())

        if not subs:
            # Fallback: treat standalone question-like lines as the plan.
            subs = [
                raw.strip().strip("*").strip()
                for raw in text.splitlines()
                if raw.strip() and "?" in raw and not raw.strip().startswith("