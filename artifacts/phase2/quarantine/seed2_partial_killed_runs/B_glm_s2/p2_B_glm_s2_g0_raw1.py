"""Repair harness: greedy SQL generation, execution, and up to three error-feedback rounds that feed database error messages back to the frozen solver for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G0(SQLHarness):
    """Error-feedback repair loop wrapped around the frozen text-to-SQL solver.

    Control flow for every ``solve`` call:

    1. One greedy generation (temperature 0) of a candidate query.
    2. Canonicalisation plus a read-only safety gate (a single
       SELECT / WITH ... SELECT statement only, no multi-statements).
    3. Execution of the candidate against the target database.
    4. On any failure (empty extraction, safety violation, or a database
       error) every failed query *together with its exact error message*
       is placed in a repair prompt and the same frozen solver regenerates
       a corrected query.
    5. Steps 2-4 repeat for up to ``MAX_ROUNDS`` attempts, stopping early
       if the solver repeats a query that has already failed.
    """

    MAX_ROUNDS = 4  # 1 initial generation + up to 3 repair rounds

    SYSTEM_PROMPT = (
        "You are a precise text-to-SQL translator. "
        "Reply with a single SQLite SELECT statement and nothing else."
    )

    # ------------------------------------------------------------------ #
    # main entry point                                                   #
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        attempts = []   # [(sql, error_message)] of every failed round
        seen = set()    # normalised text of queries already tried
        prompt = self._initial_prompt(question)

        for _ in range(self.MAX_ROUNDS):
            # 1. generate one candidate with the frozen solver ---------------
            raw = self._generate(prompt)
            try:
                sql = bridge.extract_sql(raw) or ""
            except Exception:
                sql = ""
            sql = self._canonical(sql)

            # 2. duplicate guard: a repeated query means no progress ---------
            key = self._normal_form(sql)
            if key in seen:
                break
            seen.add(key)

            # 3. safety gate, then execute against the real database ---------
            error = self._static_check(sql)
            if error is None:
                result = self._run(sql)
                if result.get("ok"):
                    return sql  # executed cleanly: ship it
                error = str(result.get("error") or "query failed to execute")

            # 4. record the failure and build a repair prompt that shows -----
            #    the model its own broken SQL plus the exact DB error --------
            attempts.append((sql, error))
            prompt = self._repair_prompt(question, attempts)

        # 5. nothing ever executed cleanly: return the least-bad candidate ---
        return self._fallback(attempts)

    # ------------------------------------------------------------------ #
    # prompt builders                                                    #
    # ------------------------------------------------------------------ #

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Task: write ONE SQLite query that answers the question.\n"
            "Rules:\n"
            "- Output a single read-only SELECT (or WITH ... SELECT) statement.\n"
            "- Use only the tables and columns that appear in the schema.\n"
            "- Wrap the query in a