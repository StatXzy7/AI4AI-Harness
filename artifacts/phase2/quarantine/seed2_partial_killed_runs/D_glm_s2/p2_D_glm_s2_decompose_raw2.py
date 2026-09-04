"""Harness that decomposes the question into an ordered list of sub-questions, answers each with its own small schema-grounded LLM call (executing the intermediate SQL so later steps see real results), then assembles and validates the final SQL."""

import re

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2Decompose"]


class P2P2DGlmS2Decompose(SQLHarness):
    """Step-by-step decomposition harness: plan -> per-step SQL -> assemble -> validate."""

    MAX_STEPS = 6          # hard cap on planned sub-questions
    MAX_REPAIRS = 2        # repair attempts for a failing final candidate
    PREVIEW_ROWS = 5       # intermediate rows shown to later steps
    PREVIEW_CHARS = 60     # per-cell truncation in result previews
    MAX_ERROR_CHARS = 300  # truncation for execution error messages

    # ------------------------------------------------------------------ prompts
    DECOMPOSE_SYSTEM = (
        "You are a precise query planner for text-to-SQL. Break the user's question "
        "into a short ordered sequence of concrete sub-questions. Each sub-question "
        "must be answerable by one SQL query against the given schema, and later "
        "sub-questions may build on the answers to earlier ones. Output ONLY a "
        "numbered list, one sub-question per line, with no preamble and no SQL."
    )

    STEP_SYSTEM = (
        "You are an expert SQL writer answering exactly ONE sub-question of a larger "
        "task. Use only the tables and columns in the given schema and keep the query "
        "minimal. Output ONLY one SQL statement and nothing else."
    )

    ASSEMBLE_SYSTEM = (
        "You are an expert SQL writer. You are given an original question plus the "
        "ordered sub-questions, the SQL written for each, and previews of their "
        "results. Merge those steps into ONE final SQL statement that answers the "
        "original question, preferring nested or joined sub-queries over hardcoded "
        "values. Output ONLY the final SQL statement."
    )

    REPAIR_SYSTEM = (
        "You are an expert SQL debugger. Fix the given failing SQL so it executes "
        "without error against the schema while still answering the original "
        "question. Output ONLY the corrected SQL statement."
    )

    DIRECT_SYSTEM = (
        "You are an expert text-to-SQL translator. Write one SQL statement that "
        "answers the user's question using only the given schema. Output ONLY the "
        "SQL statement."
    )

    _ITEM_RE = re.compile(
        r"^\s*(?:\**(?:step\s*)?\d{1,2}\**\s*[.)\]:-]|[-*\u2022])\s*(\S.*)$", re.I
    )
    _BARE_NUM_RE = re.compile(r"^\s*\**(?:step\s*)?\d{1,2}\**\s*[.)\]:]?\s*$", re.I)

    # ------------------------------------------------------------------ pipeline
    def solve(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return ""

        # Phase 1 -- plan: split the question into ordered sub-questions.
        steps = self._decompose(question)
        if len(steps) < 2:
            # Decomposition added nothing (or failed): fall back to single-shot.
            return self._direct(question)

        # Phase 2 -- solve: one small LLM call per sub-question; each intermediate
        # SQL is executed so later steps are grounded in real database results.
        findings = []
        for idx, subq in enumerate(steps, 1):
            sql = self._answer_step(question, subq, findings)
            findings.append(self._run_step(idx, subq, sql))

        # Phase 3 -- assemble: merge the per-step SQL into one final statement.
        candidate = self._assemble(question, findings)

        # Phase 4 -- validate (and repair) against the live database.
        final = self._validate(question, findings, candidate)
        if final:
            return final

        # Fallback: single-shot solve if the decomposed pipeline did not validate.
        return self._direct(question)

    # ------------------------------------------------------------------ phases
    def _decompose(self, question):
        prompt = (
            "Database schema:\n%s\n\n"
            "Question:\n%s\n\n"
            "Decompose this question into 2 to %d ordered sub-questions. Keep each "
            "sub-question short and concrete; the last one should produce the final "
            "answer requested by the question."
            % (self._schema_text(), question, self.MAX_STEPS)
        )
        text = self._llm_text(prompt, self.DECOMPOSE_SYSTEM)
        return self._parse_steps(text)

    def _answer_step(self, question, subq, findings):
        prompt = (
            "Database schema:\n%s\n\n"
            "Original question:\n%s\n\n"
            "Steps solved so far:\n%s\n\n"
            "Now answer ONLY sub-question %d:\n%s\n\n"
            "Write one SQL statement for this sub-question. If it depends on earlier "
            "steps, reuse their SQL as a sub-query or the concrete values seen in "
            "their result previews."
            % (self._schema_text(), question, self._format_findings(findings),
               len(findings) + 1, subq)
        )
        text = self._llm_text(prompt, self.STEP_SYSTEM)
        return self._extract(text)

    def _assemble(self, question, findings):
        prompt = (
            "Database schema:\n%s\n\n"
            "Original question:\n%s\n\n"
            "Ordered sub-question solutions:\n%s\n\n"
            "Combine these steps into ONE final SQL statement that answers the "
            "original question."
            % (self._schema_text(), question, self._format_findings(findings))
        )
        text = self._llm_text(prompt, self.ASSEMBLE_SYSTEM)
        return self._extract(text)

    def _validate(self, question, findings, sql):
        """Execute the candidate; repair up to MAX_REPAIRS times. Return SQL or None."""
        current = (sql or "").strip()
        if not current:
            return None
        for attempt in range(self.MAX_REPAIRS + 1):
            res = self._safe_execute(current)
            if res.get("ok"):
                return current
            if attempt == self.MAX_REPAIRS:
                break
            current = self._repair(
                question, findings, current, str(res.get("error") or "unknown error")
            )
            if not current:
                return None
        return None

    def _repair(self, question, findings, sql, error):
        error = error[: self.MAX_ERROR_CHARS]
        prompt = (
            "Database schema:\n%s\n\n"
            "Original question:\n%s\n\n"
            "Ordered sub-question solutions (context):\n%s\n\n"
            "Failing SQL:\n%s\n\n"
            "Execution error:\n%s\n\n"
            "Return the corrected SQL."
            % (self._schema_text(), question, self._format_findings(findings),
               sql, error)
        )
        text = self._llm_text(prompt, self.REPAIR_SYSTEM)
        return self._extract(text)

    def _direct(self, question):
        prompt = (
            "Database schema:\n%s\n\n"
            "Question:\n%s\n\n"
            "Write the SQL statement that answers this question."
            % (self._schema_text(), question)
        )
        sql = self._extract(self._llm_text(prompt, self.DIRECT_SYSTEM))
        validated = self._validate(question, [], sql)
        if validated:
            return validated
        return sql  # best effort even if it does not execute

    # ------------------------------------------------------------------ steps
    def _run_step(self, idx, subq, sql):
        """Execute one sub-question's SQL and record the outcome for later steps."""
        record = {"index": idx, "subquestion": subq, "sql": sql or "", "result": ""}
        if not record["sql"]:
            record["result"] = "(no SQL produced)"
            return record
        res = self._safe_execute(record["sql"])
        if res.get("ok"):
            rows = res.get("rows") or []
            record["result"] = (
                "executed OK, %d row(s); preview: %s" % (len(rows), self._preview(rows))
            )
        else:
            err = str(res.get("error") or "unknown error")[: self.MAX_ERROR_CHARS]
            record["result"] = "execution error: %s" % err
        return record

    def _parse_steps(self, text):
        """Parse a numbered list of sub-questions; only real list items are accepted."""
        steps = []
        for raw in str(text or "").splitlines():
            line = raw.strip()
            if not line or self._BARE_NUM_RE.match(line):
                continue
            m = self._ITEM_RE.match(line)
            if not m:
                continue  # skip prose / headers / anything that is not a list item
            item = m.group(1).strip().strip('"').strip()
            if len(item) < 3:
                continue
            if item.lower() in {s.lower() for s in steps}:
                continue  # drop duplicates
            steps.append(item)
            if len(steps) >= self.MAX_STEPS:
                break
        return steps

    # ------------------------------------------------------------------ helpers
    def _format_findings(self, findings):
        if not findings:
            return "(none)"
        blocks = []
        for f in findings:
            blocks.append(
                "%d. Sub-question: %s\n   SQL: %s\n   Result: %s"
                % (f["index"], f["subquestion"], f["sql"] or "(none)", f["result"])
            )
        return "\n".join(blocks)

    def _preview(self, rows):
        rows = rows or []
        if not rows:
            return "[]"
        shown = []
        for row in rows[: self.PREVIEW_ROWS]:
            if isinstance(row, dict):
                cells = ["%s=%s" % (k, self._shorten(v)) for k, v in row.items()]
            elif isinstance(row, (list, tuple)):
                cells = [self._shorten(c) for c in row]
            else:
                cells = [self._shorten(row)]
            shown.append("(" + ", ".join(cells) + ")")
        suffix = " ..." if len(rows) > self.PREVIEW_ROWS else ""
        return "; ".join(shown) + suffix

    def _shorten(self, value):
        text = "NULL" if value is None else str(value)
        text = text.replace("\n", " ")
        if len(text) > self.PREVIEW_CHARS:
            text = text[: self.PREVIEW_CHARS] + "..."
        return text

    def _schema_text(self):
        return str(getattr(self, "schema", "") or "")

    def _safe_execute(self, sql):
        try:
            return self.execute(sql) or {}
        except Exception as exc:  # executor failures must never break the pipeline
            return {"ok": False, "rows": [], "error": str(exc)}

    def _llm_text(self, prompt, system):
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:  # tolerate narrower LLM signatures
            out = self.llm(prompt, system)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if isinstance(out, dict):
            out = out.get("text") or out.get("content") or out.get("response") or ""
        return str(out).strip() if out else ""

    def _extract(self, text):
        text = str(text or "").strip()
        if not text:
            return ""
        sql = ""
        try:
            sql = str(bridge.extract_sql(text) or "").strip()
        except Exception:
            sql = ""
        if not sql:
            m = re.search(r"