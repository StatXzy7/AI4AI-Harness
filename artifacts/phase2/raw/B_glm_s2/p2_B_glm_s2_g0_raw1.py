"""Greedy SQL generation hardened by an execution-feedback repair loop that executes each candidate query and feeds its database error back to the model for corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

_SYSTEM_INITIAL = (
    "You are an expert SQL analyst. Using only the tables and columns defined in the "
    "provided schema, write exactly one SQL query that answers the user's question."
)

_SYSTEM_REPAIR = (
    "You are an expert SQL analyst repairing a query that failed to execute against "
    "the database. Use the reported error to produce a corrected query that runs cleanly."
)

_MAX_ERR_CHARS = 400


class P2P2BGlmS2G0(SQLHarness):
    """Generate greedily, execute, and repair: every failed query is regenerated
    after its SQL, its database error, and a targeted hint are fed back into
    the prompt (up to REPAIR_ROUNDS corrective rounds)."""

    #: corrective regeneration rounds available after the initial generation
    REPAIR_ROUNDS = 3

    # ------------------------------------------------------------------ #
    # control flow
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        question = (question or "").strip()

        failures = []  # [(sql, error)] history of every failed attempt
        last_sql = ""  # most recent non-empty candidate (final fallback)

        # Initial greedy generation.
        sql = self._generate(self._initial_prompt(question))

        # Execute-and-repair loop: up to REPAIR_ROUNDS corrective
        # regenerations, each conditioned on the errors observed so far.
        for round_idx in range(self.REPAIR_ROUNDS + 1):
            sql = self._normalize(sql)
            if sql:
                last_sql = sql

            # Cheap pre-execution gate (empty / non-read-only output).
            error = self._gate(sql)

            # Real execution against the database.
            if error is None:
                ok, error = self._run(sql)
                if ok:
                    return sql  # executes cleanly -> done

            failures.append((sql, error))
            if round_idx >= self.REPAIR_ROUNDS:
                break  # repair budget exhausted

            # Repair round: feed SQL + DB error + hint of every failure back in.
            sql = self._generate(
                self._repair_prompt(question, failures),
                system=_SYSTEM_REPAIR,
            )

        # Nothing executed cleanly: return the latest non-empty attempt.
        return last_sql

    # ------------------------------------------------------------------ #
    # prompting
    # ------------------------------------------------------------------ #

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self._schema_block()}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. Use only tables and "
            "columns that appear in the schema, and prefer simple, standard SQL.\n"
            "Reply with a single SQL query in a