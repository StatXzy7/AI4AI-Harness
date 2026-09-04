"""Solves Text-to-SQL by decomposing the question into ordered sub-questions, answering each with its own small validated LLM call, then assembling the per-step SQL fragments into one final query."""


import re
from typing import Any, Dict, List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS1Decompose(SQLHarness):
    """Prompt-to-Code harness (GLM, strategy 1): plan -> solve steps -> assemble.

    The decomposition strategy is realized in the control flow of :meth:`solve`,
    not merely in the prompts:

    1. **Plan**    -- one LLM call turns the question into an ordered list of
       sub-questions (parsed, deduplicated, capped).
    2. **Solve**   -- each sub-question gets its OWN small LLM call producing a
       single ``SELECT``; every fragment is executed against the database,
       repaired once on error, and its result preview is fed forward to the
       next step.
    3. **Assemble**-- a final LLM call fuses the validated fragments (via CTEs
       or subqueries) into one SQL statement, which is executed, repaired once
       on error, and falls back to a direct single-shot query as a last resort.
    """

    MAX_STEPS = 6              # cap on sub-questions per question (cost control)
    MAX_ROW_PREVIEW = 3        # rows shown to the model as step evidence
    MAX_ASSEMBLY_REPAIRS = 1   # repair attempts for the assembled final SQL

    # ------------------------------------------------------------------ #
    # infrastructure helpers
    # ------------------------------------------------------------------ #

    @property
    def _schema_text(self) -> str:
        return str(getattr(self, "schema", "") or "").strip() or "(no schema provided)"

    def _llm(self, prompt: str, system: str = "") -> str:
        """One LLM call, hardened against odd return shapes."""
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            try:  # executor with a narrower signature
                out = self.llm(prompt)
            except Exception:
                return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return "" if out is None else str(out)

    def _exec(self, sql: str) -> Dict[str, Any]:
        """Execute SQL defensively; always returns a well-formed result dict."""
        if not sql or not sql.strip():
            return {"ok": False, "rows": [], "error": "empty SQL"}
        try:
            res = self.execute(sql)
        except Exception as exc:  # noqa: BLE001 - a harness must never crash
            return {"ok": False, "rows": [], "error": "executor raised: %s" % exc}
        if not isinstance(res, dict):
            return {"ok": False, "rows": [], "error": "executor returned non-dict"}
        rows = res.get("rows") or []
        if not isinstance(rows, list):
            rows = []
        return {
            "ok": bool(res.get("ok", False)),
            "rows": rows,
            "error": str(res.get("error") or ""),
        }

    def _preview(self, rows: List[Any]) -> str:
        """Short textual preview of intermediate rows for prompt context."""
        if not rows:
            return "(no rows)"
        head = "; ".join(str(r) for r in rows[: self.MAX_ROW_PREVIEW])
        if len(rows) > self.MAX_ROW_PREVIEW:
            head += " ... (%d rows total)" % len(rows)
        return head

    # ------------------------------------------------------------------ #
    # stage 1: decomposition
    # ------------------------------------------------------------------ #

    def decompose(self, question: str) -> List[str]:
        """Split *question* into an ordered list of sub-questions (one LLM call)."""
        prompt = (
            "You are a SQL query planner.\n"
            "Break the user's question into the shortest ordered list of simple "
            "sub-questions that must each be answered before the full question "
            "can be answered.\n"
            "Rules:\n"
            "- Output ONLY numbered sub-questions, one per line "
            f"(at most {self.MAX_STEPS}).\n"
            "- Each sub-question must be answerable by one simple SQL SELECT.\n"
            "- Later steps may depend on earlier steps' results.\n"
            "- No SQL, no explanations, no extra text.\n\n"
            f"Database schema:\n{self._schema_text}\n\n"
            f"User question: {question}\n\n"
            "Numbered sub-questions:"
        )
        text = self._llm(prompt, system="You plan SQL queries as ordered sub-questions.")
        steps = self._parse_steps(text)

        # Deduplicate while preserving execution order.
        seen: set = set()
        ordered: List[str] = []
        for s in steps:
            key = re.sub(r"\s+", " ", s.strip().lower())
            if key and key not in seen:
                seen.add(key)
                ordered.append(s.strip())
        ordered = ordered[: self.MAX_STEPS]
        return ordered or [question]

    def _parse_steps(self, text: str) -> List[str]:
        """Parse numbered (or, failing that, bulleted) sub-question lists."""
        numbered: List[str] = []
        for raw in (text or "").splitlines():
            line = raw.strip().strip("*#").strip()
            if not line:
                continue
            m = re.match(
                r"^(?:step\s*)?(\d{1,2})\s*[.):\-]\s*(\S.*)$",
                line,
                flags=re.IGNORECASE,
            )
            if m:
                numbered.append(m.group(2).strip())
            elif numbered and line[:1].islower():
                numbered[-1] += " " + line  # wrapped continuation of previous step
        if len(numbered) >= 2:
            return numbered

        # Fallback: bulleted or plain lines (skip headers ending in ':').
        bullets = [
            re.sub(r"^[-*\u2022]\s+", "", ln.strip())
            for ln in (text or "").splitlines()
            if ln.strip() and not ln.strip().endswith(":")
        ]
        bullets = [b for b in bullets if len(b) > 3]
        if len(bullets) >= 2:
            return bullets
        return numbered

    # ------------------------------------------------------------------ #
    # stage 2: one small LLM call per sub-question
    # ------------------------------------------------------------------ #

    def answer_step(
        self,
        question: str,
        subq: str,
        idx: int,
        total: int,
        history: List[Tuple[str, str, Dict[str, Any]]],
    ) -> Tuple[str, Dict[str, Any]]:
        """Answer a single sub-question with a small, validated LLM call."""
        ctx = ""
        if history:
            ctx = (
                "Steps already solved (reuse their SQL rather than redoing them):\n"
            )
            for j, (prev_q, prev_sql, prev_res) in enumerate(history, 1):
                status = "ok" if prev_res["ok"] else "failed: %s" % prev_res["error"]
                ctx += (
                    "%d. %s\n"
                    "   SQL: %s\n"
                    "   result [%s]: %s\n"
                    % (j, prev_q, prev_sql or "(none)", status,
                       self._preview(prev_res["rows"]))
                )
            ctx += "\n"

        prompt = (
            "You are a precise SQL writer.\n"
            "Write ONE simple SQLite SELECT statement that answers ONLY the "
            "current step below (not the whole original question).\n\n"
            f"Database schema:\n{self._schema_text}\n\n"
            f"Original question (context only): {question}\n\n"
            f"{ctx}"
            f"Current step {idx}/{total}: {subq}\n\n"
            "Output exactly one SQL SELECT statement (a