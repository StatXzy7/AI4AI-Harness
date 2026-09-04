"""
Wraps a frozen Text-to-SQL solver by parsing the 'Hint:' line and restating its constraints as hard requirements before SQL generation.
"""
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2DMinimaxS2HintGuard(SQLHarness):
    # Strategy-specific parameters
    HINT_PREFIX = "Hint:"
    MAX_HINT_REPROMPT_TRIES = 1

    def _extract_hint(self, question: str) -> str:
        """Extract the hint text from the question if present."""
        # Look for 'Hint:' line (case-insensitive), possibly at start of line
        match = re.search(
            r"(?im)^\s*" + re.escape(self.HINT_PREFIX) + r"\s*(.+?)(?:\n|$)",
            question,
        )
        if match:
            return match.group(1).strip()
        return ""

    def _strip_hint_from_question(self, question: str) -> str:
        """Remove the 'Hint:' line from the question for cleaner prompting."""
        return re.sub(
            r"(?im)^\s*" + re.escape(self.HINT_PREFIX) + r"\s*.+?(?:\n|$)",
            "",
            question,
        ).strip()

    def _build_constraints_text(self, hint: str) -> str:
        """Restate the hint's constraints as hard requirements."""
        if not hint:
            return ""
        return (
            "HARD REQUIREMENTS (these are mandatory and override any default interpretation):\n"
            f"- The following hint MUST be satisfied: {hint}\n"
            "- Treat each clause of the hint as a binding constraint.\n"
            "- If the hint specifies a column, table, predicate, ordering, limit, or aggregation, "
            "your SQL MUST include it exactly.\n"
            "- Do not relax, omit, or reinterpret any part of the hint.\n"
        )

    def _build_system_prompt(self, constraints_text: str) -> str:
        """Compose the system prompt that enforces hint adherence."""
        base = (
            "You are a precise Text-to-SQL generator. "
            "Given a natural language question and a database schema, "
            "produce a single valid SQL query that answers the question. "
            "Output ONLY the SQL statement, with no commentary or markdown fences."
        )
        if constraints_text:
            return base + "\n\n" + constraints_text
        return base

    def _generate_candidate_sql(self, prompt: str, system: str) -> str:
        """Call the frozen LLM and extract SQL from its raw output."""
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)
        if not sql:
            sql = raw.strip()
        return sql

    def _sql_satisfies_hint(self, sql: str, hint: str) -> bool:
        """Best-effort structural check that the SQL reflects the hint constraints."""
        if not hint:
            return True
        sql_lower = sql.lower()
        hint_lower = hint.lower()

        # Tokenize hint into potential SQL keywords/identifiers
        candidate_tokens = re.findall(r"[a-zA-Z_][a-zA-Z_0-9]*", hint_lower)

        # If no recognizable tokens, accept (cannot disprove)
        if not candidate_tokens:
            return True

        # Heuristic: at least one substantive hint token must appear in the SQL
        # (filters out very common stopwords which would trivially match)
        stopwords = {
            "the", "a", "an", "of", "to", "in", "on", "for", "and", "or",
            "is", "are", "be", "by", "with", "that", "this", "it", "as",
            "from", "use", "using", "should", "must", "only", "at", "least",
        }
        substantive = [t for t in candidate_tokens if t not in stopwords and len(t) > 2]
        if not substantive:
            return True

        for token in substantive:
            if token in sql_lower:
                return True

        # None of the substantive hint tokens appear in SQL -> likely violation
        return False

    def solve(self, question: str) -> str:
        """
        Strategy: Parse the 'Hint:' line from the question, restate its constraints as
        hard requirements, and enforce them in the control flow (not only in the prompt):
          1. Extract hint text.
        2. Strip hint from question for the actual question body.
        3. Build a system prompt that treats the hint as binding.
        4. Generate SQL candidate via the frozen solver.
        5. Verify hint constraints appear in the SQL; if not, retry once with a
           strengthened system message that explicitly demands the hint tokens.
        6. Return the final SQL string (best-effort; even if verification fails,
           return the last candidate so the pipeline continues).
        """
        hint = self._extract_hint(question)
        question_body = self._strip_hint_from_question(question)

        constraints_text = self._build_constraints_text(hint)
        system_prompt = self._build_system_prompt(constraints_text)

        # Initial candidate
        candidate = self._generate_candidate_sql(question_body, system_prompt)

        # Control-flow enforcement: if hint exists and SQL appears to ignore it,
        # retry once with an even more explicit reminder.
        if hint and not self._sql_satisfies_hint(candidate, hint):
            reinforced_system = system_prompt + (
                "\n\nREMINDER: Your previous attempt did not reflect the hint. "
                f"You MUST include references consistent with: {hint}. "
                "Re-read the hint carefully and ensure every mentioned entity, "
                "predicate, or clause is present in your SQL."
            )
            retry_candidate = self._generate_candidate_sql(
                question_body, reinforced_system
            )
            if retry_candidate:
                candidate = retry_candidate

        return candidate