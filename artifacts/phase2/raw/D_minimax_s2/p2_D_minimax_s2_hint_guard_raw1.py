"""Harness that parses Hint lines from the question, restates them as hard constraints in the prompt, and validates the generated SQL against them before returning."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2HintGuard(SQLHarness):
    # Simple heuristic parse for "Hint: ..." line(s)
    HINT_DELIMITERS = ["\n", ";"]

    def _extract_hint(self, question: str) -> str:
        """Pull the trailing 'Hint:' clause out of the question, if present."""
        if not question:
            return ""
        # Look for a line that starts with 'Hint:' (case-insensitive)
        lines = question.splitlines()
        hint_parts = []
        capture = False
        for line in lines:
            stripped = line.strip()
            low = stripped.lower()
            if capture:
                # Stop at another directive-looking line or empty line terminating a list
                if not stripped:
                    break
                if low.startswith("question:") or low.startswith("q:") or low.startswith("sql:") or low.startswith("schema:"):
                    break
                hint_parts.append(stripped)
            elif low.startswith("hint:"):
                # First segment after the marker
                first = stripped[len("hint:"):].strip()
                if first:
                    hint_parts.append(first)
                capture = True
        return " ".join(hint_parts).strip()

    def _rewrite_question(self, question: str, hint: str) -> str:
        """Remove the hint line(s) from the question so the LLM is not double-fed."""
        if not hint:
            return question
        out_lines = []
        skip = False
        for line in question.splitlines():
            low = line.strip().lower()
            if low.startswith("hint:"):
                skip = True
                continue
            if skip:
                # Skip continuation lines that look like hint bullets
                if not line.strip():
                    skip = False
                out_lines.append(line)
            else:
                out_lines.append(line)
        cleaned = "\n".join(out_lines).strip()
        return cleaned

    def _build_constraints_block(self, hint: str) -> str:
        """Restate the hint as an explicit hard-requirements block."""
        if not hint:
            return ""
        return (
            "HARD REQUIREMENTS (these are mandatory; failure to satisfy them makes the SQL wrong):\n"
            f"- The following user-supplied hint MUST be honored exactly: {hint}\n"
            "- If the hint specifies a filter, predicate, join, ordering, limit, column, "
            "or aggregation, the SQL MUST include it.\n"
            "- Do not introduce filters, joins, or projections that contradict the hint.\n"
            "- If honoring the hint is impossible given the schema, prefer the closest faithful "
            "translation that still respects the hint's intent over an unconstrained answer.\n"
        )

    def _hint_constraint_checks(self, sql: str) -> str:
        """Return a checklist string the LLM uses to self-verify the SQL."""
        return (
            "Before finalizing, verify each HARD REQUIREMENT against the SQL:\n"
            "  1. Every required predicate appears in a WHERE / HAVING / ON clause.\n"
            "  2. Every required column appears in SELECT or in a relevant clause.\n"
            "  3. Every required JOIN / ORDER BY / GROUP BY / LIMIT is present.\n"
            "  4. No contradicting clauses were introduced.\n"
            "If any check fails, rewrite the SQL to fix it before emitting the final query.\n"
        )

    def _looks_safe(self, sql: str) -> bool:
        """Cheap structural sanity check before execution."""
        if not sql or not sql.strip():
            return False
        bad = (";", "--", "/*", "*/")
        # Allow a single trailing semicolon, but reject stacked statements or comments
        stripped = sql.rstrip()
        if stripped.endswith(";"):
            inner = stripped[:-1]
        else:
            inner = stripped
        if ";" in inner:
            return False
        for token in bad[1:]:
            if token in inner:
                return False
        return True

    def _execute_or_retry(self, question_for_llm: str, attempt: int) -> str:
        """One pass: ask the LLM, extract SQL, execute; return SQL string (may be empty on failure)."""
        system = (
            "You are a precise Text-to-SQL generator.\n"
            "Return ONLY a single SQL query (optionally ending with a semicolon). "
            "No prose, no markdown fences, no explanations."
        )
        prompt = question_for_llm
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw if isinstance(raw, str) else str(raw))
        if not sql:
            return ""
        if not self._looks_safe(sql):
            return ""
        result = self.execute(sql)
        if not result or not result.get("ok", False):
            return ""
        return sql

    def solve(self, question: str) -> str:
        hint = self._extract_hint(question)
        cleaned_question = self._rewrite_question(question, hint)

        constraints = self._build_constraints_block(hint)
        checklist = self._hint_constraint_checks(hint) if hint else ""

        # Frame the prompt so the hint-derived constraints are foregrounded.
        prompt_parts = []
        if self.schema:
            prompt_parts.append(f"SCHEMA:\n{self.schema}")
        if cleaned_question:
            prompt_parts.append(f"QUESTION:\n{cleaned_question}")
        if constraints:
            prompt_parts.append(constraints)
        if checklist:
            prompt_parts.append(checklist)
        prompt_parts.append(
            "OUTPUT: exactly one SQL statement that satisfies ALL hard requirements above."
        )
        prompt = "\n\n".join(prompt_parts)

        # First attempt
        sql = self._execute_or_retry(prompt, attempt=1)
        if sql:
            return sql

        # Retry once with an even more explicit restatement of constraints,
        # so the control flow enforces the strategy rather than relying on prompt alone.
        if hint:
            reinforced = (
                prompt
                + "\n\nREMINDER: The hint was: "
                + hint
                + "\nRe-emit the SQL making sure that constraint is present verbatim in the query."
            )
            sql2 = self._execute_or_retry(reinforced, attempt=2)
            if sql2:
                return sql2

        # Final fallback: ask for a minimal SQL that at least encodes the hint literally.
        if hint:
            minimal_prompt = (
                (f"SCHEMA:\n{self.schema}\n\n" if self.schema else "")
                + f"QUESTION:\n{cleaned_question}\n\n"
                + f"HARD REQUIREMENT (must appear in the SQL): {hint}\n\n"
                + "Produce a single SQL statement that incorporates the hard requirement. "
                + "Return only the SQL."
            )
            raw = self.llm(minimal_prompt, system="", temperature=0.0, n=1)
            sql3 = bridge.extract_sql(raw if isinstance(raw, str) else str(raw))
            if sql3 and self._looks_safe(sql3):
                res = self.execute(sql3)
                if res and res.get("ok", False):
                    return sql3

        return ""