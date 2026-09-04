"""Greedy SQL drafting plus an execution-repair loop: every database error is fed back to the frozen solver for a corrective regeneration (up to 3 rounds)."""

# MECHANISM: repair

from typing import Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G1(SQLHarness):
    """Draft SQL greedily, execute it, and on failure feed the engine error back
    to the solver for a corrected regeneration, up to MAX_REPAIR_ROUNDS times."""

    MAX_REPAIR_ROUNDS = 3

    SYSTEM = (
        "You are an expert SQLite analyst. Answer with a single valid SQL "
        "query and nothing else."
    )

    def solve(self, question: str) -> str:
        schema = self.schema if isinstance(self.schema, str) else str(self.schema or "")

        # ---- Stage 1: single greedy draft ------------------------------------
        sql = self._generate(self._draft_prompt(schema, question))

        # ---- Stage 2: execute; on failure, repair with the error fed back ----
        ok, error = self._try_execute(sql)
        if ok:
            return sql

        failed = {sql: error}
        for _ in range(self.MAX_REPAIR_ROUNDS):
            candidate = self._generate(
                self._repair_prompt(schema, question, sql, error)
            )
            # Empty draft, or a repeat of an already-failing query: stop early,
            # further rounds would only burn identical calls.
            if not candidate or candidate in failed:
                break
            ok, error = self._try_execute(candidate)
            if ok:
                return candidate
            failed[candidate] = error
            sql = candidate  # newest failing attempt becomes the repair target

        # Nothing executed cleanly; hand back the most recent attempt.
        return sql

    # ------------------------------------------------------------------ helpers

    def _draft_prompt(self, schema: str, question: str) -> str:
        return (
            "Database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. Use only tables and "
            "columns that appear in the schema above. Reply with the query in a "
            "