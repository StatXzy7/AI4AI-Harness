"""Solves text-to-SQL by decomposing the question into an ordered list of sub-questions, answering each sub-question with its own small LLM call over the schema, and assembling the per-step SQL answers into one final query."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS0Decompose(SQLHarness):
    """Decompose -> solve each sub-question -> assemble -> verify/repair."""

    MAX_SUBS = 5          # cap on the number of ordered sub-questions
    SUB_RETRIES = 1       # execution-error retries per sub-question
    FINAL_REPAIRS = 2     # execution-error retries on the assembled SQL
    PREVIEW_ROWS = 3      # rows of sub-answer output fed forward
    PREVIEW_CHARS = 160   # truncation for previews/errors inside prompts

    DECOMPOSER_SYSTEM = (
        "You decompose a database question into an ordered list of simpler "
        "sub-questions. Each sub-question must be answerable by a single SQL "
        "SELECT over the given schema, and answering them in order must make "
        "the original question easy to assemble. Reply with ONLY a JSON array "
        "of 2-5 short sub-question strings, no commentary."
    )

    SUBSOLVER_SYSTEM = (
        "You are a careful SQL writer. Given a schema, the original question "
        "for context, and exactly one sub-question, write a single SQL SELECT "
        "that answers that sub-question. Reply with only the SQL."
    )

    ASSEMBLER_SYSTEM = (
        "You combine solved sub-questions into one final SQL query. Reuse the "
        "sub-answer SQL as CTEs, subqueries, or filter steps. Reply with only "
        "the final SQL."
    )

    # ----------------------------------------------------------- plumbing

    def _call(self, prompt, system):
        """One small LLM call; normalize whatever shape the bridge returns."""
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            out = self.llm(prompt, system)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if isinstance(out, dict):
            out = out.get("text") or out.get("content") or out.get("response") or ""
        return out.strip() if isinstance(out, str) else ""

    def _sql_of(self, text):
        """Extract a SQL string from an LLM reply via the bridge."""
        if not text:
            return ""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            return ""
        return sql.strip() if isinstance(sql, str) else ""

    def _run(self, sql):
        """Execute a candidate query defensively."""
        if not sql:
            return {"ok": False, "rows": [], "error": "empty SQL"}
        try:
            res = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": "executor raised: %s" % exc}
        if not isinstance(res, dict):
            return {"ok": False, "rows": [], "error": "executor returned non-dict"}
        return {
            "ok": bool(res.get("ok")),
            "rows": list(res.get("rows") or []),
            "error": str(res.get("error") or ""),
        }

    def _preview(self, res):
        """Compact one-line description of a sub-answer's execution."""
        if not res["ok"]:
            err = res["error"] or "unknown error"
            return "execution failed: %s" % err[: self.PREVIEW_CHARS]
        rows = res["rows"][: self.PREVIEW_ROWS]
        if not rows:
            return "executed ok, 0 rows"
        cells = []
        for row in rows:
            s = str(row)
            if len(s) > self.PREVIEW_CHARS:
                s = s[: self.PREVIEW_CHARS - 3] + "..."
            cells.append(s)
        return "executed ok, sample rows: %s" % " | ".join(cells)

    # -------------------------------------------------------- step 1: split

    def _decompose(self, question):
        prompt = (
            "Database schema:\n%s\n\nQuestion: %s\n\n"
            "Break the question into 2 to %d ordered sub-questions, each "
            "answerable by one SQL SELECT over this schema, that together "
            "cover everything needed to answer the original question. Reply "
            'with ONLY a JSON array of strings, e.g. ["step 1", "step 2"].'
            % (self.schema, question, self.MAX_SUBS)
        )
        subs = self._parse_subquestions(self._call(prompt, self.DECOMPOSER_SYSTEM))
        if not subs:
            # Degenerate decomposition: the whole question is the single step.
            subs = [question]
        return subs[: self.MAX_SUBS]

    @staticmethod
    def _parse_subquestions(text):
        """Parse a JSON array, else numbered/bulleted lines, else nothing."""
        if not text:
            return []
        subs = []
        m = re.search(r"\[[\s\S]*\]", text)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, (list, tuple)):
                        item = item[0] if item else ""
                    s = str(item).strip()
                    if s:
                        subs.append(s)
        if not subs:
            for line in text.splitlines():
                mm = re.match(r"^(?:\d{1,2}[).:\-]|[-*\u2022])\s+(.*\S)\s*$", line.strip())
                if mm:
                    subs.append(mm.group(1))
        seen, uniq = set(), []
        for s in subs:
            key = s.lower()
            if key not in seen:
                seen.add(key)
                uniq.append(s)
        return uniq

    # -------------------------------------------------- step 2: solve each

    def _solve_sub(self, question, sub, idx, total, history):
        if history:
            prev = ["Previously solved sub-questions:"]
            for j, (q, sql, note) in enumerate(history, 1):
                prev.append("%d. %s" % (j, q))
                prev.append("   SQL: %s" % (sql or "(none)"))
                prev.append("   result: %s" % note)
            prev_ctx = "\n".join(prev)
        else:
            prev_ctx = "(this is the first sub-question)"

        prompt = (
            "Database schema:\n%s\n\n"
            "Original question (context only): %s\n\n"
            "%s\n\n"
            "Sub-question %d of %d: %s\n\n"
            "Write one SQL SELECT that answers only this sub-question. You "
            "may reuse the earlier SQL as a subquery or CTE. Reply with only "
            "the SQL."
            % (self.schema, question, prev_ctx, idx + 1, total, sub)
        )
        sql = self._sql_of(self._call(prompt, self.SUBSOLVER_SYSTEM))
        res = self._run(sql)

        tries = 0
        while not res["ok"] and sql and tries < self.SUB_RETRIES:
            tries += 1
            fix = (
                "Database schema:\n%s\n\n"
                "Original question: %s\n\n"
                "Sub-question: %s\n\n"
                "Your SQL:\n%s\n\n"
                "Executor error: %s\n\n"
                "Write a corrected SQL SELECT for this sub-question. Reply "
                "with only the SQL."
                % (self.schema, question, sub, sql, res["error"] or "unknown error")
            )
            fixed = self._sql_of(self._call(fix, self.SUBSOLVER_SYSTEM))
            if not fixed or fixed == sql:
                break
            sql = fixed
            res = self._run(sql)
        return sql, res

    # ---------------------------------------------------- step 3: assemble

    def _assemble(self, question, history):
        if history:
            trace = []
            for j, (q, sql, note) in enumerate(history, 1):
                trace.append("Sub-question %d: %s" % (j, q))
                trace.append("  SQL: %s" % (sql or "(none)"))
                trace.append("  result: %s" % note)
            trace_ctx = "\n".join(trace)
        else:
            trace_ctx = "(no sub-answers available)"

        prompt = (
            "Database schema:\n%s\n\n"
            "Original question: %s\n\n"
            "Ordered sub-questions with their SQL answers and results:\n%s\n\n"
            "Write ONE final SQL SELECT that answers the original question, "
            "reusing the sub-answer SQL (WITH clauses, subqueries, filters) "
            "where helpful. Reply with only the final SQL."
            % (self.schema, question, trace_ctx)
        )
        return self._sql_of(self._call(prompt, self.ASSEMBLER_SYSTEM))

    def _repair(self, question, history, sql