"""Repair-loop Text-to-SQL harness: generate a candidate query, execute it, and feed execution failures back to the LLM for bounded regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS0G0(SQLHarness):
    """Generate -> execute -> repair loop.

    A single greedy generation is only the first step. Every candidate query is
    actually run against the database; whenever execution fails (or returns
    zero rows) the error/feedback is written into a repair prompt so the frozen
    solver rewrites its own query. The loop is bounded and always returns the
    best query seen: the first row-producing query, else the first error-free
    query, else the last candidate.
    """

    SYSTEM = (
        "You are an expert SQLite query writer. Given a database schema and a "
        "natural-language question, produce exactly one valid SQLite SELECT "
        "query. Output only the SQL: no explanation, no markdown fences."
    )

    MAX_ATTEMPTS = 4  # total execute() calls allowed per question

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite SELECT query that answers the question. "
            "Output only the SQL."
        )

    def _repair_prompt(self, question: str, failed_sql: str, feedback: str, prior_failures: list) -> str:
        lines = [
            "Database schema:",
            self.schema,
            "",
            f"Question: {question}",
            "",
            "The previously generated SQL query did not work.",
            "Failed query:",
            failed_sql,
            "",
            f"What happened when it was executed: {feedback}",
        ]
        earlier = prior_failures[:-1][-2:]
        if earlier:
            lines += ["", "Earlier attempts also failed; do not repeat these mistakes:"]
            for sql, err in earlier:
                lines.append(f"- {sql}  ==>  {err}")
        lines += [
            "",
            "Rewrite the query so it executes correctly on SQLite and answers "
            "the question. Output only the corrected SQL.",
        ]
        return "\n".join(lines)

    def solve(self, question: str) -> str:
        candidate = bridge.extract_sql(
            self.llm(self._initial_prompt(question), system=self.SYSTEM, temperature=0.0)
        )
        first_candidate = candidate
        best_valid = ""        # first query that executed without error
        prior_failures = []    # (sql, feedback) pairs, most recent last

        for _ in range(self.MAX_ATTEMPTS):
            if not candidate:
                # Extraction failed: ask again, sampling slightly to escape the rut.
                candidate = bridge.extract_sql(
                    self.llm(self._initial_prompt(question), system=self.SYSTEM, temperature=0.3)
                )
                if not candidate:
                    continue

            result = self.execute(candidate)

            if result.get("ok"):
                if result.get("rows"):
                    return candidate  # success: non-empty result set
                if not best_valid:
                    best_valid = candidate
                feedback = (
                    "The query executed without errors but returned zero rows. "
                    "Re-check the chosen tables/columns, join conditions, and "
                    "filter values against the schema and the question."
                )
            else:
                feedback = f"Execution error: {result.get('error', 'unknown error')}"

            prior_failures.append((candidate, feedback))
            repair_prompt = self._repair_prompt(question, candidate, feedback, prior_failures)

            fixed = bridge.extract_sql(
                self.llm(repair_prompt, system=self.SYSTEM, temperature=0.0)
            )
            if fixed and fixed.strip() == candidate.strip():
                # The solver repeated the same broken query; resample to break the tie.
                fixed = bridge.extract_sql(
                    self.llm(repair_prompt, system=self.SYSTEM, temperature=0.5)
                )
                if fixed and fixed.strip() == candidate.strip():
                    fixed = ""  # force a fresh generation on the next round
            candidate = fixed

        return best_valid or candidate or first_candidate