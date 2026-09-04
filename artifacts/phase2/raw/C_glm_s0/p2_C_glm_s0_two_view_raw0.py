"""Generate two independent SQL formulations of the question (a JOIN-based query and a subquery/CTE-based query), execute both against the database, and return the first formulation whose execution yields rows, preferring the JOIN-based one when both succeed."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS0TwoView(SQLHarness):
    """Text-to-SQL harness that cross-checks two independently written views of the same question."""

    name = "P2P2CGlmS0TwoView"

    SYSTEM = "You are an expert SQLite analyst. You write exact, executable SQLite queries."

    JOIN_STYLE = (
        "Formulate the answer as a JOIN-based query: combine every table you "
        "need in the FROM clause using explicit JOIN ... ON clauses (or a "
        "comma-separated FROM list with WHERE join conditions). Do NOT use "
        "nested subqueries unless a join genuinely cannot express the answer."
    )

    SUBQUERY_STYLE = (
        "Formulate the answer as a subquery-based query: rely on nested "
        "subqueries (IN, NOT IN, EXISTS, NOT EXISTS, or scalar subqueries) "
        "or on WITH ... AS common table expressions. Do NOT use JOIN clauses "
        "unless a subquery genuinely cannot express the answer."
    )

    # ------------------------------------------------------------------ LLM

    def _call(self, prompt: str) -> str:
        try:
            out = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        except TypeError:
            # Fallback for llm signatures that do not accept the n argument.
            out = self.llm(prompt, system=self.SYSTEM, temperature=0.0)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if out is None:
            return ""
        return str(out)

    def _formulate(self, question: str, style: str) -> str:
        """Ask the weak solver for one SQL formulation under a given structural style."""
        prompt = (
            "Database schema:\n"
            "----------------\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"{style}\n\n"
            "Return exactly one SQLite SELECT statement, enclosed in a "
            "