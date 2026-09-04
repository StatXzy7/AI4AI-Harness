"""Execution-guided repair harness: generate SQL, execute it against the database, and feed errors back for iterative regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G3(SQLHarness):
    """Closed-loop generate -> execute -> repair Text-to-SQL harness.

    Instead of trusting a single greedy generation, this harness runs the
    produced SQL against the database. Execution errors (and suspicious
    zero-row results) are fed back into a repair prompt, and the model is
    asked for a corrected query. The loop stops as soon as a query executes
    and returns rows; otherwise the best query seen so far is returned.
    """

    MAX_ATTEMPTS = 5

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL translator. "
            "You output exactly one valid SQLite SELECT query and nothing else."
        )

        sql = bridge.extract_sql(
            self._generate(self._initial_prompt(question), system=system, temperature=0.0)
        )

        last_candidate = sql or ""
        clean_fallback = ""
        saw_empty = False
        failed = set()

        for attempt in range(self.MAX_ATTEMPTS):
            candidate = (sql or "").strip()
            if not candidate:
                sql = self._repair(
                    question, "",
                    "Your previous reply contained no SQL query at all.",
                    system, attempt,
                )
                continue

            last_candidate = candidate
            outcome = self.execute(candidate)

            if outcome.get("ok"):
                rows = outcome.get("rows") or []
                if rows:
                    return candidate
                # Executable but empty: keep as fallback, challenge it once.
                clean_fallback = candidate
                if saw_empty:
                    # Two clean-but-empty runs: accept that the answer is empty.
                    return candidate
                saw_empty = True
                feedback = (
                    "The query executed successfully but returned ZERO rows. "
                    "This usually means over-restrictive WHERE conditions, wrong join keys, "
                    "or string literals that do not match the stored values. "
                    "Re-read the question, verify every filter against the schema, and fix "
                    "the query. If you are certain zero rows is the correct answer, "
                    "return the same query unchanged."
                )
            else:
                feedback = "SQLite error: " + (outcome.get("error") or "unknown error")
                failed.add(candidate)

            sql = self._repair(question, candidate, feedback, system, attempt)
            if (sql or "").strip() in failed:
                # The model repeated an already-failed query; force a different rewrite.
                sql = self._repair(
                    question, candidate,
                    feedback + "\nDo NOT repeat the same failing query; rewrite it differently.",
                    system, attempt + 2,
                )

        return clean_fallback or last_candidate

    # ------------------------------------------------------------------
    def _initial_prompt(self, question: str) -> str:
        return (
            "Using the database schema below, write a single SQLite SELECT query "
            "that answers the question.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Rules:\n"
            "- Use only tables and columns present in the schema.\n"
            "- Return ONLY the SQL query: no markdown fences, no commentary.\n\n"
            "SQL:"
        )

    def _repair(self, question: str, bad_sql: str, feedback: str,
                system: str, attempt: int) -> str:
        prompt = (
            "A SQLite query written for the question below needs to be fixed.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Previous SQL:\n{bad_sql or '(no query was produced)'}\n\n"
            f"Database feedback:\n{feedback}\n\n"
            "Write a corrected SQLite query that resolves this feedback. "
            "Return ONLY the corrected SQL query: no markdown fences, no commentary."
        )
        # Slightly raise temperature on later repairs to escape repeated mistakes.
        temperature = min(0.1 + 0.1 * max(attempt, 0), 0.5)
        return bridge.extract_sql(
            self._generate(prompt, system=system, temperature=temperature)
        )

    def _generate(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)