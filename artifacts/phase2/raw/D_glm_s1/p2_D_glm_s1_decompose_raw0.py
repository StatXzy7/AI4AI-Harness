"""Decompose the input question into an ordered chain of sub-questions, answer each one with its own small LLM call whose SQL fragment is executed and whose results chain into the next prompt, then assemble the verified fragments into a single final SQL statement that is executed and repaired until it runs."""

from ..harness_base import SQLHarness
from .. import bridge

import re

__all__ = ["P2P2DGlmS1Decompose"]


class P2P2DGlmS1Decompose(SQLHarness):
    """Decompose-then-assemble Text-to-SQL solver (P2P2D, GLM stage 1).

    The strategy lives in the control flow, not only in the prompts:

      Stage 1  DECOMPOSE  one LLM call plans the question into an ordered,
                          numbered list of small sub-questions (regex-parsed,
                          with a whole-question fallback).
      Stage 2  ANSWER     one small LLM call per sub-question, strictly in
                          order; every fragment is executed against the DB
                          and its status / row sample is chained forward as
                          context for the next sub-question; a failing
                          fragment gets one bounded error-feedback retry.
      Stage 3  ASSEMBLE   one LLM call composes the verified fragments
                          (subqueries / joins / CTEs) into the final SQL.
      Stage 4  VERIFY     the final SQL is executed; while it errors it is
                          repaired (bounded attempts), with a single
                          direct-shot last resort.
    """

    name = "P2P2DGlmS1Decompose"

    # tunables
    max_subquestions = 5    # upper bound on planned sub-questions
    max_sub_retries = 1     # error-feedback retries per sub-question
    max_repairs = 2         # repair attempts on the assembled SQL
    sample_rows = 3         # rows echoed back to the model as evidence
    sample_chars = 300      # truncation for the echoed row sample
    max_subq_chars = 500    # ignore absurdly long planned sub-questions

    # ------------------------------------------------------------------
    # low-level plumbing
    # ------------------------------------------------------------------
    def _call(self, prompt, system="", temperature=0.0):
        """One invocation of the frozen LLM, normalised to plain text."""
        try:
            out = self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if out is None:
            return ""
        return str(out).strip()

    def _extract(self, text):
        """Pull a single clean SQL statement out of an LLM reply."""
        try:
            sql = bridge.extract_sql(text or "")
        except Exception:
            return ""
        if not sql:
            return ""
        sql = str(sql).strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    def _execute(self, sql):
        """Safe wrapper around self.execute -> (ok, error, rows)."""
        if not sql:
            return False, "empty SQL", []
        try:
            res = self.execute(sql)
        except Exception as exc:
            return False, "executor raised: %s" % exc, []
        if not isinstance(res, dict):
            return False, "malformed executor response", []
        return (bool(res.get("ok")),
                str(res.get("error") or ""),
                (res.get("rows") or []))

    def _summarize(self, sql):
        """Run a fragment and describe the outcome for the next prompt."""
        ok, error, rows = self._execute(sql)
        if not ok:
            return "FAILED (%s)" % (error or "unknown error")
        sample = repr(rows[: self.sample_rows])
        if len(sample) > self.sample_chars:
            sample = sample[: self.sample_chars] + "..."
        return "ran OK, %d row(s), sample: %s" % (len(rows), sample)

    def _fmt_answered(self, answered):
        """Render the ordered (sub-question, SQL, execution) chain."""
        if not answered:
            return "(none)"
        lines = []
        for i, a in enumerate(answered, 1):
            lines.append("%d. %s\n   SQL: %s\n   execution: %s"
                         % (i, a["q"], a["sql"] or "(none)", a["status"]))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Stage 1: decomposition
    # ------------------------------------------------------------------
    def _decompose(self, question):
        system = ("You are a precise SQL query planner. "
                  "Output only the numbered list of sub-questions, nothing else.")
        prompt = (
            "Database schema (SQLite):\n%s\n\n"
            "User question:\n%s\n\n"
            "Split this question into 2 to %d ORDERED sub-questions. Rules:\n"
            "- each sub-question is answered by ONE simple SQL SELECT over the schema above;\n"
            "- write plain English sub-questions (no SQL, no 'see step 1');\n"
            "- order them so later sub-questions can reuse earlier answers;\n"
            "- together they must cover everything needed for the original question.\n"
            "Output exactly one sub-question per line, numbered like:\n"
            "1. ...\n2. ..."
            % (self.schema or "", question, self.max_subquestions)
        )
        text = self._call(prompt, system)

        # primary parse: numbered lines
        numbered = []
        for line in text.splitlines():
            m = re.match(r"^\s*\d+\s*[.)\]:-]\s*(\S.*)$", line)
            if m:
                numbered.append(m.group(1).strip())

        # fallback parse: bullet / plain lines if numbering was ignored
        items = numbered
        if not items:
            for line in text.splitlines():
                item = line.strip().lstrip("-*\u2022").strip()
                if item:
                    items.append(item)

        # dedupe (case-insensitive), drop junk, preserve order
        subs, seen = [], set()
        for item in items:
            item = item.strip().strip("*_").strip()
            if not item or len(item) > self.max_subq_chars:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            subs.append(item)

        if not subs:
            subs = [question]
        return subs[: self.max_subquestions]

    # ------------------------------------------------------------------
    # Stage 2: answer one sub-question with a small, focused LLM call
    # ------------------------------------------------------------------
    def _answer_subquestion(self, question, sub_q, idx, total, answered):
        context = ""
        if answered:
            context = ("Sub-questions already answered, in order:\n"
                       "%s\n\n" % self._fmt_answered(answered))

        system = ("You write minimal, correct SQLite. "
                  "Reply with exactly one SQL statement in a