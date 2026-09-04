"""Decomposes the question into an ordered list of sub-questions, answers each sub-question with its own small LLM call to produce verified sub-SQL pieces, then assembles those pieces into the final SQL."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS0Decompose"]


class P2P2CGlmS0Decompose(SQLHarness):
    """Prompt-to-Plan-to-Prompt-to-Code decomposition harness.

    The strategy lives in the CONTROL FLOW of :meth:`solve`, not just in prompts:

    1. PLAN    -- one LLM call turns the question into an ordered list of
                  SQL-answerable sub-questions.
    2. SOLVE   -- a real Python loop makes ONE small LLM call per sub-question,
                  and every produced sub-SQL is executed against the database
                  so each building block is verified or flagged as broken.
    3. COMPOSE -- one LLM call stitches the verified pieces into the final SQL,
                  which is executed; on failure a repair call, a direct
                  single-shot call, and finally the newest verified sub-SQL
                  piece are tried in order.
    """

    name = "P2P2CGlmS0Decompose"

    MAX_SUBQUESTIONS = 5   # hard cap on decomposition length
    MAX_PRIOR_CONTEXT = 4  # earlier sub-answers shown to a sub-call

    # ------------------------------------------------------------------ #
    # low-level plumbing
    # ------------------------------------------------------------------ #

    def _llm(self, prompt, system=""):
        """One small LLM call; always returns a (possibly empty) string."""
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if not isinstance(out, str):
            out = str(out)
        return out.strip()

    def _extract(self, text):
        """bridge.extract_sql with defensive handling."""
        try:
            sql = bridge.extract_sql(text or "")
        except Exception:
            return ""
        return (sql or "").strip()

    def _run_sql(self, sql):
        """Execute SQL defensively; always returns {'ok', 'rows', 'error'}."""
        if not sql:
            return {"ok": False, "rows": [], "error": "empty SQL"}
        try:
            res = self.execute(sql)
        except Exception as exc:  # a broken SQL must never crash the harness
            return {"ok": False, "rows": [], "error": "exception: %s" % exc}
        if not isinstance(res, dict):
            return {"ok": False, "rows": [], "error": "bad execute() result"}
        return {
            "ok": bool(res.get("ok")),
            "rows": res.get("rows") or [],
            "error": str(res.get("error") or ""),
        }

    @staticmethod
    def _clip(text, limit=120):
        text = " ".join(str(text).split())
        return text if len(text) <= limit else text[: limit - 3] + "..."

    def _sample_rows(self, rows, k=3):
        if not rows:
            return "(no rows)"
        shown = "; ".join(self._clip(r, 100) for r in list(rows)[:k])
        return shown + (" ..." if len(rows) > k else "")

    @staticmethod
    def _parse_json(text):
        """Best-effort extraction of the first JSON object in `text`."""
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(text[start: end + 1])
            except Exception:
                pass
        return None

    @staticmethod
    def _newest_verified(answers):
        """Newest sub-SQL that actually executed OK (or None)."""
        for a in reversed(answers):
            if a["ok"] and a["sql"]:
                return a["sql"]
        return None

    # ------------------------------------------------------------------ #
    # STEP 1: PLAN -- decompose the question
    # ------------------------------------------------------------------ #

    def _decompose(self, question):
        system = "You decompose database questions into ordered, SQL-answerable sub-questions."
        prompt = "\n".join([
            "Decompose the user's question about the database into an ORDERED list of "
            "simpler sub-questions.",
            "",
            "Rules:",
            "- Each sub-question must be answerable by ONE SQL SELECT on this schema.",
            "- Order them so that later sub-questions can build on earlier ones.",
            "- Use at most %d sub-questions." % self.MAX_SUBQUESTIONS,
            "- Use exactly 1 sub-question if the question is already simple.",
            "- Do NOT write SQL and do NOT answer; only list sub-questions.",
            "",
            "Schema:",
            str(self.schema),
            "",
            "User question: %s" % question,
            "",
            'Reply with exactly one JSON object: {"subquestions": ["...", "..."]}',
        ])
        raw = self._llm(prompt, system)

        subs = []
        obj = self._parse_json(raw)
        if isinstance(obj, dict):
            cand = obj.get("subquestions")
            if not isinstance(cand, list):
                cand = obj.get("sub_questions") or obj.get("steps")
            if isinstance(cand, list):
                subs = [str(s).strip() for s in cand if str(s).strip()]

        if not subs:  # fallback: numbered plain-text list
            subs = [
                m.group(1).strip()
                for m in re.finditer(r"^\s*\d+[\.\):]\s*(.+?)\s*$", raw, re.MULTILINE)
            ]

        if not subs:  # undecomposable: the whole question is the single part
            subs = [question]

        return subs[: self.MAX_SUBQUESTIONS]

    # ------------------------------------------------------------------ #
    # STEP 2: SOLVE -- one small LLM call per sub-question
    # ------------------------------------------------------------------ #

    def _collect_subanswers(self, question, subs):
        answers = []
        for idx, sub in enumerate(subs):
            sql = self._answer_subquestion(
                question,
                subs,
                idx,
                sub,
                answers[-self.MAX_PRIOR_CONTEXT:],
            )
            res = self._run_sql(sql)  # verify every building block on the real DB
            answers.append({
                "sub": sub,
                "sql": sql,
                "ok": res["ok"],
                "rows": res["rows"],
                "error": res["error"],
            })
        return answers

    def _answer_subquestion(self, question, subs, idx, sub, prior):
        system = "You are a precise text-to-SQL engine. Output SQL only."
        lines = [
            "You are solving ONE sub-question of a larger question.",
            "",
            "Schema:",
            str(self.schema),
            "",
            "Original question: %s" % question,
            "",
            "Ordered sub-questions:",
        ]
        for j, s in enumerate(subs, 1):
            lines.append("%d. %s" % (j, s))
        lines += [
            "",
            "Current sub-question (%d of %d): %s" % (idx + 1, len(subs), sub),
            "",
        ]
        if prior:
            lines.append("Earlier sub-questions and their SQL (for reference):")
            for p in prior:
                if p["ok"]:
                    status = "executed OK; rows: %s" % self._sample_rows(p["rows"])
                else:
                    status = "execution FAILED: %s" % self._clip(p["error"], 90)
                lines.append(
                    "- %s\n  SQL: %s\n  %s" % (p["sub"], p["sql"] or "(none)", status)
                )
        else:
            lines.append("(This is the first sub-question.)")
        lines += [
            "",
            "Write ONE SQL SELECT statement that answers ONLY the current sub-question.",
            "SQL:",
        ]
        raw = self._llm("\n".join(lines), system)
        return self._extract(raw)

    # ------------------------------------------------------------------ #
    # STEP 3: COMPOSE -- assemble the verified pieces
    # ------------------------------------------------------------------ #

    def _assemble(self, question, answers):
        system = "You are a precise text-to-SQL assembler. Output SQL only."
        lines = [
            "Combine the sub-SQL pieces below into ONE final SQL SELECT that answers "
            "the ORIGINAL question.",
            "",
            "Schema:",
            str(self.schema),
            "",
            "Original question: %s" % question,
            "",
            "Ordered sub-question pieces:",
        ]
        for i, a in enumerate(answers, 1):
            if a["ok"]:
                status = "executed OK; rows: %s" % self._sample_rows(a["rows"])
            else:
                status = "execution FAILED: %s" % self._clip(a["error"], 90)
            lines += [
                "%d. Sub-question: %s" % (i, a["sub"]),
                "   SQL: %s" % (a["sql"] or "(none)"),
                "   %s" % status,
            ]
        lines += [
            "",
            "Rules:",
            "- You may reuse the sub-SQLs verbatim (e.g. as CTEs) or rewrite from scratch.",
            "- The final SQL must answer the ORIGINAL question, not a single sub-question.",
            "- Prefer pieces that executed OK; a failed piece is a hint, not a constraint.",
            "- Output only the final SQL.",
        ]
        raw = self._llm("\n".join(lines), system)
        return self._extract(raw)

    # ------------------------------------------------------------------ #
    # fallbacks
    # ------------------------------------------------------------------ #

    def _repair(self, question, sql, error, answers):
        system = "You are a precise text-to-SQL fixer. Output SQL only."
        pieces = "\n".join(
            "%d. %s -> %s" % (i, a["sql"] or "(none)", "ok" if a["ok"] else "failed")
            for i, a in enumerate(answers, 1)
        )
        prompt = "\n".join([
            "A final SQL statement failed against the database. Fix it.",
            "",
            "Schema:",
            str(self.schema),
            "",
            "Original question: %s" % question,
            "",
            "Broken SQL:",
            sql,
            "",
            "Database error: %s" % (self._clip(error, 200) or "unknown error"),
            "",
            "Verified sub-SQL pieces:",
            pieces or "(none)",
            "",
            "Output only the corrected final SQL.",
        ])
        raw = self._llm(prompt, system)
        return self._extract(raw)

    def _direct(self, question):
        system = "You are a precise text-to-SQL engine. Output SQL only."
        prompt = "\n".join([
            "Write ONE SQL SELECT statement that answers the question.",
            "",
            "Schema:",
            str(self.schema),
            "",
            "Question: %s" % question,
            "",
            "SQL:",
        ])
        raw = self._llm(prompt, system)
        return self._extract(raw)

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return ""

        # ---- STEP 1: PLAN -------------------------------------------------
        subs = self._decompose(question)

        # ---- STEP 2: SOLVE (one small LLM call per sub-question) -----------
        answers = self._collect_subanswers(question, subs)

        # ---- STEP 3: COMPOSE ----------------------------------------------
        final = self._assemble(question, answers)
        final_res = self._run_sql(final)
        if final_res["ok"]:
            return final

        # ---- fallback ladder ----------------------------------------------
        repaired = ""
        if final:
            repaired = self._repair(question, final, final_res["error"], answers)
            if repaired and repaired != final and self._run_sql(repaired)["ok"]:
                return repaired

        # With a single sub-question its verified SQL *is* the answer.
        if len(answers) == 1 and answers[0]["ok"] and answers[0]["sql"]:
            return answers[0]["sql"]

        direct = self._direct(question)
        if direct and self._run_sql(direct)["ok"]:
            return direct

        # Newest verified building block.
        piece = self._newest_verified(answers)
        if piece:
            return piece

        # Nothing verified: return the best-effort string we produced.
        for sql in (final, repaired, direct):
            if sql:
                return sql
        for a in reversed(answers):
            if a["sql"]:
                return a["sql"]
        return ""