"""Greedy SQL generation wrapped in an execution-repair loop that runs each candidate query and feeds database errors and empty results back to the frozen solver for corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G7(SQLHarness):
    """Execution-feedback repair loop around a frozen text-to-SQL solver.

    Control flow (a real change versus a single greedy call):

    1. Ask the frozen solver for one SQL query (greedy, temperature 0).
    2. Check the query is read-only SELECT-shaped, then execute it against the
       target database via ``self.execute``.
    3. If execution errors, returns zero rows, or the reply contained no
       extractable SQL, build a *repair prompt* carrying the schema, the
       question, and the full history of (SQL, database feedback) pairs, and
       let the solver regenerate a corrected query.
    4. Repeat until a query succeeds or ``MAX_LLM_CALLS`` solver calls are used.

    Return priority: the first query that executes and returns rows, else the
    first query that executes cleanly, else the last non-empty extracted SQL.
    """

    MAX_LLM_CALLS = 3
    READ_ONLY_PREFIXES = ("select", "with", "values")

    SYSTEM_PROMPT = (
        "You are a precise SQLite expert. You translate a natural-language "
        "question into exactly one read-only SQLite SELECT query that uses only "
        "the tables and columns given in the schema."
    )

    # ------------------------------------------------------------------ #
    # main control flow
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        attempts = []        # repair memory: [{"sql": str, "feedback": str}]
        clean_ok_sql = None  # first SQL that executed without error
        last_sql = ""        # last non-empty SQL extracted from a reply

        for _ in range(self.MAX_LLM_CALLS):
            if attempts:
                prompt = self._repair_prompt(question, schema, attempts)
            else:
                prompt = self._initial_prompt(question, schema)

            raw = self._generate(prompt)
            sql = self._clean(bridge.extract_sql(raw))
            if sql:
                last_sql = sql

            # Failure mode 1: nothing that looks like SQL came back.
            if not sql:
                attempts.append({
                    "sql": (raw or "").strip()[:500] or "(empty reply)",
                    "feedback": (
                        "No SQL statement could be extracted from the previous "
                        "answer. Reply with exactly one SQLite SELECT query "
                        "inside a