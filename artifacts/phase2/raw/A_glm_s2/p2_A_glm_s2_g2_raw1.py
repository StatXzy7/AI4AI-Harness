"""Repair-loop text-to-SQL harness: a greedy first draft is executed against the real database and, whenever execution fails, the exact database error is fed back to the LLM for up to three corrective regeneration rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G2(SQLHarness):
    """Execute-then-repair harness.

    Control flow (a real change over a single greedy call):
      1. One greedy LLM call turns (schema, question) into a candidate query.
      2. The candidate is executed against the database.
      3. On failure, the failing SQL *and* the exact database error are packed
         into a repair prompt; the LLM regenerates the query.
      4. Steps 2-3 repeat under a bounded repair budget, stopping early on
         success, on an empty regeneration, or on an unproductive rewrite
         (with one temperature escalation before giving up on a stalled fix).
    """

    MAX_REPAIRS = 3
    STALL_TEMPERATURE = 0.5
    MAX_ERROR_CHARS = 500

    SYSTEM_INITIAL = (
        "You are an expert text-to-SQL translator targeting SQLite. "
        "Use only the tables and columns that appear in the given schema."
    )
    SYSTEM_REPAIR = (
        "You are an expert SQLite debugger. You repair failing queries using "
        "only the tables and columns that appear in the given schema."
    )

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        sql = self._initial_generation(question)

        temperature = 0.0
        stalled = False

        for attempt in range(self.MAX_REPAIRS + 1):
            # ---- execute the current candidate -------------------------- #
            if sql:
                previous_sql = sql
                result = self._run(sql)
            else:
                previous_sql = "(no SQL produced)"
                result = {
                    "ok": False,
                    "rows": [],
                    "error": "No SQL statement could be extracted from the previous answer.",
                }

            if result.get("ok"):
                return sql  # clean execution: we are done

            if attempt >= self.MAX_REPAIRS:
                break  # repair budget exhausted

            # ---- feed the execution error back for regeneration --------- #
            error = self._clip(str(result.get("error") or "unknown execution error"))
            repaired = self._repair_generation(question, previous_sql, error, temperature)

            if not repaired:
                break  # nothing usable came back; keep the last candidate

            if self._norm(repaired) == self._norm(sql):
                # Deterministic rut: nudge once with a higher temperature,
                # then stop if the rewrite is still unproductive.
                if stalled:
                    break
                stalled = True
                temperature = self.STALL_TEMPERATURE
                continue

            sql = repaired
            stalled = False
            temperature = 0.0

        return sql or "SELECT 1;"

    # ------------------------------------------------------------------ #
    # LLM stages
    # ------------------------------------------------------------------ #

    def _initial_generation(self, question: str) -> str:
        prompt = (
            f"Database schema:\n{self._schema_block()}\n\n"
            f"Question: {question}\n\n"
            "Write exactly one SQLite query that answers the question. "
            "Output only the query inside a single