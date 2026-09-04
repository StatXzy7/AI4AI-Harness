"""Decomposes the question into an ordered list of sub-questions, answers each one with its own small scoped LLM call (executing each sub-SQL to gather evidence), then assembles the pieces into a single final SQL statement."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS2Decompose(SQLHarness):
    """Plan -> answer sub-questions separately -> assemble -> validate/repair."""

    MAX_SUBQUESTIONS = 6
    MAX_EVIDENCE_ROWS = 5

    _NUMBERED_RE = re.compile(r"^\s*(\d{1,2})\s*[.):\-]\s*(\S.*)$")

    # ------------------------------------------------------------------ solve

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return ""

        # ---- Stage 1: break the question into ORDERED sub-questions.
        sub_questions = self._decompose(question)

        # ---- Stage 2: answer each sub-question with its own SMALL LLM call.
        # Each call is deliberately scoped: schema + that one sub-question +
        # evidence from earlier sub-answers (never the whole task at once).
        sub_results = []
        for idx, sub_q in enumerate(sub_questions, start=1):
            sql, evidence, ok = self._answer_subquestion(sub_q, idx, sub_results)
            sub_results.append(
                {
                    "index": idx,
                    "question": sub_q,
                    "sql": sql,
                    "ok": ok,
                    "evidence": evidence,
                }
            )

        # ---- Stage 3: assemble the sub-answers into the final SQL.
        final_sql = self._assemble(question, sub_results)
        if not final_sql:
            final_sql = self._best_sub_sql(sub_results)
        if not final_sql:
            final_sql = self._direct(question)
        if not final_sql:
            return ""

        # ---- Stage 4: validate by executing; repair once if it fails.
        if self._is_valid(final_sql):
            return final_sql
        repaired = self._repair(question, sub_results, final_sql)
        if repaired and self._is_valid(repaired):
            return repaired
        # A single sub-question that executed cleanly beats a broken assembly.
        if len(sub_results) == 1 and sub_results[0]["ok"] and sub_results[0]["sql"]:
            return sub_results[0]["sql"]
        return final_sql

    # ---------------------------------------------------------- stage 1: plan

    def _decompose(self, question: str):
        prompt = (
            "You are a SQL planning assistant. Break the user's question into an ORDERED list of "
            "simple sub-questions, each answerable by a single SQL query over the schema below. "
            "Keep every sub-question faithful to the original question; add nothing, drop nothing. "
            "Use as few sub-questions as possible (usually 1-4).\n"
            "Output ONLY a numbered list, one sub-question per line, like:\n"
            "1. first sub-question\n"
            "2. second sub-question\n\n"
            f"Database schema:\n{self._schema_text()}\n\n"
            f"User question: {question}"
        )
        text = self._call(prompt, system="You decompose questions into ordered SQL sub-questions.")

        subs = self._parse_numbered(text)
        if not subs:
            subs = [ln.strip(" \t-*•") for ln in (text or "").splitlines()]
            subs = [s for s in subs if len(s) > 2]

        seen, ordered = set(), []
        for s in subs:
            key = s.lower()
            if key not in seen:
                seen.add(key)
                ordered.append(s)

        if not ordered:
            ordered = [question]
        return ordered[: self.MAX_SUBQUESTIONS]

    def _parse_numbered(self, text: str):
        found = []
        for line in (text or "").splitlines():
            m = self._NUMBERED_RE.match(line)
            if m:
                item = m.group(2).strip()
                if item:
                    found.append(item)
        return found

    # -------------------------------------------------- stage 2: sub-answers

    def _answer_subquestion(self, sub_q: str, idx: int, prior_results):
        """One small LLM call that answers exactly one sub-question."""
        prompt = (
            "Write ONE SQLite SELECT statement that answers ONLY the sub-question below. "
            "Do not try to answer the whole original task.\n\n"
            f"Database schema:\n{self._schema_text()}\n\n"
        )
        prior = self._format_subresults(prior_results)
        if prior:
            prompt += (
                "Earlier sub-questions and their executed results (you may build on them via "
                "subqueries or CTEs):\n"
                f"{prior}\n\n"
            )
        prompt += f"Sub-question {idx}: {sub_q}\n\nOutput only the SQL statement."

        sql = self._extract(
            self._call(prompt, system="You answer exactly one sub-question with one SQL query.")
        )
        if not sql:
            return "", "no SQL produced", False

        res = self._run(sql)
        ok = bool(res.get("ok"))
        return sql, self._format_evidence(res), ok

    # -------------------------------------------------- stage 3: assembly

    def _assemble(self, question: str, sub_results):
        transcript = self._format_subresults(sub_results)
        prompt = (
            "You are given a database schema, a user question, and an ordered transcript of "
            "sub-questions; for each sub-question there is the SQL that was written and what it "
            "returned when executed. Write ONE final SQLite SELECT statement that answers the "
            "ORIGINAL user question by combining the sub-question SQL (subqueries, joins, or CTEs). "
            "Reuse the working pieces and rewrite the ones that failed. "
            "Output only the final SQL statement.\n\n"
            f"Database schema:\n{self._schema_text()}\n\n"
            f"Original user question: {question}\n\n"
            f"Sub-question transcript:\n{transcript}"
        )
        return self._extract(
            self._call(prompt, system="You assemble sub-question SQL into one final SQL query.")
        )

    # ------------------------------------------------- stage 4: repair

    def _repair(self, question: str, sub_results, broken_sql: str):
        res = self._run(broken_sql)
        error = self._clip(res.get("error") or "unknown execution error", 300)
        transcript = self._format_subresults(sub_results)
        prompt = (
            "The final SQL below failed when executed. Fix it so that it correctly answers the "
            "original question, reusing the sub-question transcript as needed.\n\n"
            f"Database schema:\n{self._schema_text()}\n\n"
            f"Original user question: {question}\n\n"
            f"Sub-question transcript:\n{transcript}\n\n"
            f"Broken SQL:\n{broken_sql}\n\n"
            f"Execution error: {error}\n\n"
            "Output only the corrected SQL statement."
        )
        return self._extract(self._call(prompt, system="You repair broken SQL."))

    # --------------------------------------------------------- fallbacks

    def _direct(self, question: str):
        prompt = (
            f"Database schema:\n{self._schema_text()}\n\n"
            "Write ONE SQLite SELECT statement answering the question below. "
            "Output only the SQL statement.\n\n"
            f"Question: {question}"
        )
        return self._extract(
            self._call(prompt, system="You write a single SQLite SELECT statement.")
        )

    def _best_sub_sql(self, sub_results):
        for r in reversed(sub_results):
            if r["sql"] and r["ok"]:
                return r["sql"]
        for r in reversed(sub_results):
            if r["sql"]:
                return r["sql"]
        return ""

    # -------------------------------------------------------- LLM plumbing

    def _call(self, prompt: str, system: str = "") -> str:
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if out is None:
            return ""
        return str(out).strip()

    def _extract(self, text: str) -> str:
        try:
            sql = bridge.extract_sql(text or "")
        except Exception:
            sql = ""
        sql = (sql or "").strip()
        while sql.endswith(";"):
            sql = sql[:-1].strip()
        return sql

    # ------------------------------------------------------- SQL execution

    def _run(self, sql: str):
        try:
            res = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": "executor exception: %s" % exc}
        if not isinstance(res, dict):
            return {"ok": False, "rows": [], "error": "executor returned a non-dict response"}
        return res

    def _is_valid(self, sql: str) -> bool:
        if not sql:
            return False
        return bool(self._run(sql).get("ok"))

    # -------------------------------------------------------- formatting

    def _schema_text(self) -> str:
        return (getattr(self, "schema", None) or "").strip()

    def _format_subresults(self, sub_results) -> str:
        lines = []
        for r in sub_results:
            lines.append("%d. Sub-question: %s" % (r["index"], r["question"]))
            lines.append("   SQL: %s" % (r["sql"] or "(none produced)"))
            status = "executed" if r["ok"] else "failed"
            lines.append("   Result (%s): %s" % (status, r["evidence"]))
        return "\n".join(lines)

    def _format_evidence(self, res) -> str:
        if not res.get("ok"):
            return "error: " + self._clip(res.get("error") or "unknown error", 200)
        rows = res.get("rows")
        if rows is None:
            return "executed successfully (no rows returned)"
        if not isinstance(rows, (list, tuple)):
            return "executed successfully: " + self._clip(rows, 200)

        shown = rows[: self.MAX_EVIDENCE_ROWS]
        rendered = []
        for row in shown:
            if isinstance(row, dict):
                rendered.append(
                    "{" + ", ".join("%s: %s" % (k, self._clip(v, 60)) for k, v in row.items()) + "}"
                )
            elif isinstance(row, (list, tuple)):
                rendered.append("(" + ", ".join(self._clip(x, 60) for x in row) + ")")
            else:
                rendered.append(self._clip(row, 120))

        summary = "%d row(s)" % len(rows)
        if len(rows) > self.MAX_EVIDENCE_ROWS:
            summary += ", first %d shown" % self.MAX_EVIDENCE_ROWS
        if rendered:
            return summary + ": " + " | ".join(rendered)
        return summary + " (empty)"

    @staticmethod
    def _clip(value, limit=200):
        text = "NULL" if value is None else str(value)
        return text if len(text) <= limit else text[: limit - 3] + "..."