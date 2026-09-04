"""P2P2C harness that extracts Hint constraints and enforces them as hard requirements before delegating to a frozen weak solver."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2HintGuard(SQLHarness):
    # Strategy-level instructions appended to any prompt sent to the frozen solver.
    _HINT_GUARD_INSTRUCTION = (
        "You are writing SQL under a Hint Guard protocol. The question contains a "
        "'Hint:' line that states mandatory constraints. You MUST treat every Hint "
        "constraint as a hard filter (WHERE/JOIN/HAVING/clause) that cannot be "
        "omitted, weakened, or paraphrased away. Do not relax, drop, or invert any "
        "Hint constraint even if the base question seems to ask for something "
        "broader. The Hint outranks the literal phrasing of the question when they "
        "conflict. If a constraint cannot be expressed in pure SQL (e.g., ordering "
        "by a derived expression), still represent it faithfully. Output only one "
        "SQL statement."
    )

    @staticmethod
    def _extract_hint(question: str) -> str:
        """Return the content of the 'Hint:' line, or '' if absent."""
        if not question:
            return ""
        for raw_line in question.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            # Match 'Hint:' prefix (also 'Hint :' with whitespace)
            lower = line.lower()
            if lower.startswith("hint:") or lower.startswith("hint :"):
                return line.split(":", 1)[1].strip()
        return ""

    @staticmethod
    def _enforce_single_statement(sql: str) -> str:
        """Keep only the first SQL statement, dropping trailing semicolons/comments."""
        if not sql:
            return sql
        # Strip line comments
        cleaned_lines = []
        for ln in sql.splitlines():
            stripped = ln.split("--", 1)[0]
            cleaned_lines.append(stripped)
        cleaned = "\n".join(cleaned_lines)
        # Drop everything after the first ';' that isn't inside quotes -- simple heuristic:
        # split on ';' and keep only segments that contain at least one SQL keyword.
        parts = cleaned.split(";")
        for part in parts:
            p = part.strip()
            if not p:
                continue
            upper = p.upper()
            if any(kw in upper for kw in ("SELECT", "INSERT", "UPDATE", "DELETE", "WITH")):
                return p.strip()
        return sql.strip().rstrip(";").strip()

    def _build_prompt(self, question: str, hint: str) -> str:
        """Restate Hint constraints explicitly in front of the solver prompt."""
        if hint:
            prefix = (
                "[HINT CONSTRAINTS — MUST BE SATISFIED IN THE SQL]\n"
                f"- {hint}\n"
                "[END HINT CONSTRAINTS]\n\n"
            )
        else:
            prefix = ""
        return (
            prefix
            + self._HINT_GUARD_INSTRUCTION
            + "\n\nQuestion:\n"
            + question
            + "\n\nReturn one SQL statement only."
        )

    def solve(self, question: str) -> str:
        hint = self._extract_hint(question)

        # First attempt: prompt the frozen solver with the Hint constraints restated.
        prompt_with_hint = self._build_prompt(question, hint)
        raw1 = self.llm(prompt_with_hint, system="", temperature=0.0, n=1)
        sql1 = bridge.extract_sql(raw1) or ""

        executed = self.execute(sql1) if sql1 else {"ok": False, "rows": [], "error": "empty"}

        # If the first attempt failed AND we actually had a Hint to enforce,
        # retry once with an even more forceful, constraint-locked prompt.
        if (not executed.get("ok")) and hint:
            locked_prompt = (
                "[STRICT HINT LOCK] The following Hint is non-negotiable and MUST "
                "be encoded exactly as a WHERE / JOIN / HAVING / ORDER BY clause "
                "(or equivalent) in the SQL. Do not paraphrase, weaken, drop, or "
                "reinterpret it. The Hint takes precedence over the rest of the "
                "question.\n\n"
                f"Hint: {hint}\n\n"
                "Question:\n"
                + question
                + "\n\nReply with one SQL statement only. No commentary."
            )
            raw2 = self.llm(locked_prompt, system="", temperature=0.0, n=1)
            sql2 = bridge.extract_sql(raw2) or ""
            if sql2:
                sql1 = sql2
                executed = self.execute(sql1)

        # If we still have nothing executable but no Hint existed, do a plain retry
        # with a clean prompt so the frozen solver gets a second chance.
        if (not executed.get("ok")) and not hint:
            fallback_prompt = (
                "Write one SQL query that answers the question. "
                "Output SQL only, no prose.\n\nQuestion:\n" + question
            )
            raw3 = self.llm(fallback_prompt, system="", temperature=0.0, n=1)
            sql3 = bridge.extract_sql(raw3) or ""
            if sql3:
                sql1 = sql3

        # Final sanity: ensure single statement, strip trailing semicolons.
        final_sql = self._enforce_single_statement(sql1) if sql1 else ""
        return final_sql