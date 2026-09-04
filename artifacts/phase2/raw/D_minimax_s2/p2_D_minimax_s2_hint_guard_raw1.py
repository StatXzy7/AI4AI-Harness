"""Wraps a frozen weak solver by extracting the Hint: line from the question and converting its constraints into hard pre-SQL guards before generation."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2HintGuard(SQLHarness):
    # Strategy constants controlling the harness behavior
    MAX_REGEN_ATTEMPTS = 2
    REPAIR_ON_EXEC_FAIL = True

    def solve(self, question: str) -> str:
        # self.schema: str, self.llm(prompt, system="", temperature=0.0, n=1)
        # self.execute(sql) -> {"ok": bool, "rows": [...], "error": str}
        # bridge.extract_sql(text) -> str

        # ---- 1. Parse the Hint: line from the question ----
        hint_text = self._parse_hint(question)

        # ---- 2. If we have a hint, apply pre-SQL hard guards ----
        #    * Add hint as a hard requirement in the system message
        #    * Build an enforced constraint block in the user prompt
        #    * Require the SQL to mention every constraint keyword
        if hint_text:
            system_msg = (
                "You are a Text-to-SQL generator. The user message contains a "
                "HINT block which describes HARD requirements that the SQL "
                "MUST satisfy. Treat every hint constraint as a mandatory "
                "postcondition. Never relax or reinterpret these constraints.\n"
                f"HARD REQUIREMENTS (from HINT): {hint_text}"
            )
            constraints_block = self._build_constraints_block(hint_text)
            user_prompt = (
                f"{question}\n\n"
                f"{constraints_block}\n\n"
                f"Schema:\n{self.schema}\n\n"
                "Return a single SQL query that satisfies every HARD "
                "REQUIREMENT above. The SQL must explicitly use every "
                "required table, column, operator, and literal mentioned "
                "in the HINT."
            )
        else:
            system_msg = "You are a Text-to-SQL generator. Return one SQL query."
            user_prompt = (
                f"Question: {question}\n\n"
                f"Schema:\n{self.schema}\n\n"
                "Return a single SQL query."
            )

        # ---- 3. Generate SQL, with optional regeneration loop ----
        final_sql = ""
        last_sql = ""
        last_exec = None
        for attempt in range(self.MAX_REGEN_ATTEMPTS + 1):
            raw = self.llm(user_prompt, system=system_msg, temperature=0.0, n=1)
            sql = bridge.extract_sql(raw)
            last_sql = sql

            if not sql:
                # No SQL extracted -- prompt again with a stricter message
                user_prompt = (
                    user_prompt
                    + "\n\nYour previous response did not contain a SQL "
                      "statement. Output ONLY a single SQL query."
                )
                continue

            final_sql = sql

            # ---- 4. Post-generation guard: verify SQL references hint terms ----
            if hint_text and not self._sql_respects_hint(sql, hint_text):
                user_prompt = (
                    user_prompt
                    + "\n\nREJECTED: the previous SQL did not reference "
                      "every required element from the HINT. Re-emit the "
                      "SQL ensuring every HINT element appears in the query."
                )
                continue

            break

        # ---- 5. Optional execution repair against the live DB ----
        if self.REPAIR_ON_EXEC_FAIL:
            final_sql = self._repair_with_execution(final_sql or last_sql, user_prompt, system_msg)

        return final_sql

    # ------------------------------------------------------------------
    # Hint parsing helpers
    # ------------------------------------------------------------------
    def _parse_hint(self, question: str) -> str:
        """Extract the substring following 'Hint:' (case-insensitive) if present."""
        if not question:
            return ""
        lower = question.lower()
        idx = lower.find("hint:")
        if idx == -1:
            return ""
        # Take everything after the marker up to end-of-question
        return question[idx + len("hint:"):].strip()

    def _build_constraints_block(self, hint_text: str) -> str:
        """Render the hint as an explicit HARD CONSTRAINTS block."""
        items = [line.strip("-* \t") for line in hint_text.splitlines() if line.strip()]
        if not items:
            items = [hint_text]
        body = "\n".join(f"- {item}" for item in items)
        return (
            "HARD CONSTRAINTS (the SQL MUST satisfy all of these):\n"
            f"{body}"
        )

    def _sql_respects_hint(self, sql: str, hint_text: str) -> bool:
        """Cheap structural check that SQL references tokens lifted from the hint."""
        if not sql or not hint_text:
            return True
        sql_lower = sql.lower()
        # Extract candidate tokens: words 3+ chars, skipping very common stopwords
        stopwords = {
            "the", "and", "for", "with", "that", "from", "where", "select",
            "must", "should", "use", "show", "find", "list", "all", "any",
            "hint", "this", "into", "than", "then", "when", "only",
        }
        tokens = []
        for raw in hint_text.replace(",", " ").replace(".", " ").split():
            tok = raw.strip("'\"`();:").lower()
            if len(tok) >= 3 and tok not in stopwords and not tok.isdigit():
                tokens.append(tok)
        if not tokens:
            return True
        # Require each token to appear literally in the SQL (case-insensitive)
        for tok in tokens:
            if tok not in sql_lower:
                return False
        return True

    # ------------------------------------------------------------------
    # Execution-time repair loop
    # ------------------------------------------------------------------
    def _repair_with_execution(self, sql: str, user_prompt: str, system_msg: str) -> str:
        """Try executing the SQL; if it fails, ask the LLM to repair it."""
        current = sql
        if not current:
            return ""
        for _ in range(self.MAX_REGEN_ATTEMPTS):
            result = self.execute(current)
            last_exec = result
            if result.get("ok"):
                return current
            err = result.get("error") or "unknown error"
            repair_prompt = (
                user_prompt
                + f"\n\nThe previously generated SQL failed to execute:\n"
                f"{current}\n\nDatabase error: {err}\n\n"
                "Fix the SQL so that it executes successfully while still "
                "satisfying every HARD CONSTRAINT."
            )
            raw = self.llm(repair_prompt, system=system_msg, temperature=0.0, n=1)
            repaired = bridge.extract_sql(raw)
            if not repaired or repaired == current:
                break
            current = repaired
        return current