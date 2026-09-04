"""Two-view Text-to-SQL harness: independently drafts a join-based and a subquery-based SQL formulation, executes both, and returns the first query yielding a non-empty result (join view wins ties)."""

from ..harness_base import SQLHarness
from .. import bridge

_JOIN_SYSTEM = (
    "You are an expert SQLite query engineer. You translate natural-language "
    "questions into precise, executable SQLite queries."
)

_SUBQUERY_SYSTEM = (
    "You are an expert SQLite query engineer who reasons compositionally, "
    "building answers from nested, set-oriented SELECT statements."
)

_JOIN_INSTRUCTION = (
    "Formulation requirement (view 1 - join-based): answer the question with a "
    "single flat SELECT that combines tables exclusively through explicit "
    "JOIN ... ON clauses. Do NOT use subqueries, CTEs, EXISTS, or "
    "IN (SELECT ...) predicates."
)

_SUBQUERY_INSTRUCTION = (
    "Formulation requirement (view 2 - subquery-based): answer the question "
    "with a query that expresses cross-table filtering through nested "
    "subqueries (WHERE ... IN (SELECT ...) or WHERE EXISTS (...)). Do NOT use "
    "the JOIN keyword."
)


class P2P2CKimiS2TwoView(SQLHarness):
    """Draft two independently formulated SQL candidates and keep the non-empty one.

    Control flow:
      1. Draft SQL twice under disjoint formulation constraints (join-based vs
         subquery-based) so the two candidates fail in different ways.
      2. Execute BOTH candidates against the database.
      3. Return the join-based SQL if it produced rows, else the subquery-based
         SQL if it produced rows; if neither produced rows, fall back to a
         candidate that at least executed cleanly, and finally to any draft.
    """

    def solve(self, question: str) -> str:
        # --- view 1: join-based formulation --------------------------------
        join_sql = self._draft(question, _JOIN_SYSTEM, _JOIN_INSTRUCTION)

        # --- view 2: subquery-based formulation -----------------------------
        subquery_sql = self._draft(question, _SUBQUERY_SYSTEM, _SUBQUERY_INSTRUCTION)

        # --- execute both candidates ----------------------------------------
        join_result = self._run(join_sql)
        subquery_result = self._run(subquery_sql)

        join_nonempty = join_result.get("ok") and bool(join_result.get("rows"))
        subquery_nonempty = subquery_result.get("ok") and bool(subquery_result.get("rows"))

        # --- selection: a non-empty result wins; the join view wins ties ----
        if join_nonempty:
            return join_sql
        if subquery_nonempty:
            return subquery_sql

        # Neither view returned rows: prefer whichever at least executed
        # without error (an empty-but-valid answer beats a broken one).
        if join_result.get("ok") and join_sql:
            return join_sql
        if subquery_result.get("ok") and subquery_sql:
            return subquery_sql

        # Last resort: hand back any draft we managed to extract.
        return join_sql or subquery_sql or "SELECT 1"

    # ------------------------------------------------------------------ helpers

    def _draft(self, question: str, system: str, instruction: str) -> str:
        """Ask the frozen LLM for one SQL statement under a formulation constraint."""
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"{instruction}\n\n"
            "Rules:\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- Produce exactly one SQLite statement.\n"
            "- Wrap the statement in a