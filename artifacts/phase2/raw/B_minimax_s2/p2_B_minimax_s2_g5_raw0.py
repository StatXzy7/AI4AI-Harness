"""Repair-based harness: execute the generated SQL and feed errors back to the LLM for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G5(SQLHarness):
    # Maximum number of repair attempts before falling back to the last candidate
    MAX_REPAIRS = 3

    def _build_prompt(self, question: str, previous_sql: str = "", error: str = "") -> str:
        """Compose a prompt, optionally including the previous attempt and its error."""
        parts = [
            "You are an expert SQL generator.",
            "Given the database schema below and a natural language question, "
            "produce exactly one syntactically correct SQL query that answers it.",
            "Use the provided execution feedback to fix the previous attempt when applicable.",
            "",
            "Schema:",
            self.schema,
            "",
            f"Question: {question.strip()}",
        ]
        if previous_sql:
            parts.append("")
            parts.append("Previous SQL attempt:")
            parts.append(previous_sql.strip())
        if error:
            parts.append("")
            parts.append("Execution / parse error reported by the engine:")
            parts.append(error.strip())
        parts.append("")
        parts.append("Return ONLY the corrected SQL on a single line, no commentary.")
        return "\n".join(parts)

    def _generate(self, prompt: str) -> str:
        """Call the underlying LLM once with greedy decoding and return the extracted SQL."""
        raw = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)
        # extract_sql may return "" when nothing parseable is found; fall back to the raw text
        # so the repair loop still has something concrete to feed back.
        return sql.strip() if sql else raw.strip()

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        candidate = self._generate(prompt)

        # If the very first generation produced nothing usable, just give up gracefully
        # by returning whatever the bridge extracted (likely "").
        if not candidate:
            return candidate

        for attempt in range(self.MAX_REPAIRS):
            result = self.execute(candidate)
            if result.get("ok"):
                return candidate

            # Execution failed: feed the error back and ask the model to repair.
            error_text = result.get("error") or "Unknown execution error."
            # Truncate long errors so the prompt stays bounded.
            if len(error_text) > 800:
                error_text = error_text[:800] + "..."

            repair_prompt = self._build_prompt(
                question, previous_sql=candidate, error=error_text
            )
            new_candidate = self._generate(repair_prompt)
            if not new_candidate or new_candidate.strip() == candidate.strip():
                # Model didn't change anything (or produced nothing). Stop repairing to
                # avoid an infinite loop and return the best SQL we have so far.
                return candidate
            candidate = new_candidate

        # Ran out of repair budget; return the latest candidate.
        return candidate