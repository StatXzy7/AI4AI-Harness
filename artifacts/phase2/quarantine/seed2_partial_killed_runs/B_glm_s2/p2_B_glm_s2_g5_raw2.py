"""Self-consistency voting: five varied samples are drawn from the frozen solver, and the most-voted query among those that execute cleanly is returned."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G5(SQLHarness):
    """Execution-filtered self-consistency wrapper around the weak solver.

    Control flow inside :meth:`solve` (a real change vs. one greedy call):

    1. ``N_SAMPLES`` candidate queries are drawn from the *same frozen*
       solver: the first sample is greedy (temperature 0), the remaining
       ones are sampled at a higher temperature, and each prompt carries a
       different static style hint so the candidates genuinely differ.
    2. Candidates are deduplicated on a normalized form of the SQL and get
       one vote per occurrence (plurality / self-consistency tally).
    3. Every distinct candidate is executed against the database; the
       most-voted candidate that executes cleanly wins.
    4. If nothing executes cleanly, the overall plurality candidate is
       returned as a best-effort answer.
    """

    N_SAMPLES = 5
    EXPLORATION_TEMPERATURE = 0.8

    SYSTEM = (
        "You are an expert text-to-SQL engine. "
        "Reply with a single SQL SELECT statement and nothing else."
    )

    VARIANT_HINTS = (
        "",  # unconstrained -> the solver's default formulation
        "Use explicit JOIN ... ON syntax with short table aliases.",
        "Prefer a subquery over a JOIN when it reads naturally, and copy "
        "table and column names exactly as they appear in the schema.",
        "Do not add ORDER BY or LIMIT unless the question explicitly asks "
        "for an ordering or a number of rows.",
        "Keep the query as simple as possible and re-check every identifier "
        "against the schema before answering.",
    )

    # ------------------------------------------------------------------ prompt

    def _prompt(self, question: str, index: int) -> str:
        schema = getattr(self, "schema", None)
        schema = schema if isinstance(schema, str) else ""
        hint = self.VARIANT_HINTS[index % len(self.VARIANT_HINTS)]
        lines = [
            "Database schema:",
            "",
            schema,
            "",
            "Write one SQL query that answers the following question.",
            "",
            "Question: " + question,
        ]
        if hint:
            lines += ["", "Style note: " + hint]
        lines += ["", "Return only the SQL statement."]
        return "\n".join(lines)

    # -------------------------------------------------------------- generation

    def _one_sample(self, question: str, index: int) -> str:
        """Draw a single candidate; returns '' if the call yields no SQL."""
        temperature = 0.0 if index == 0 else self.EXPLORATION_TEMPERATURE
        try:
            out = self.llm(
                self._prompt(question, index),
                system=self.SYSTEM,
                temperature=temperature,
            )
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        text = out or ""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            return ""
        sql = (sql or "").strip()
        while sql.endswith(";"):
            sql = sql[:-1].strip()
        return sql

    # --------------------------------------------------------------- selection

    @staticmethod
    def _normalize(sql: str) -> str:
        """Canonical form used to compare two candidates for voting."""
        collapsed = " ".join((sql or "").split())
        return collapsed.replace("`", "").lower()

    def _executes_cleanly(self, sql: str) -> bool:
        try:
            result = self.execute(sql)
        except Exception:
            return False
        return bool(result) and bool(result.get("ok"))

    def solve(self, question: str) -> str:
        # -- 1) draw the samples ---------------------------------------------
        samples = []
        for index in range(self.N_SAMPLES):
            sql = self._one_sample(question, index)
            if sql:
                samples.append(sql)

        if not samples:
            return ""

        # -- 2) plurality tally over normalized duplicates --------------------
        votes = {}
        representative = {}
        keys_in_order = []
        for sql in samples:
            key = self._normalize(sql)
            if key not in votes:
                votes[key] = 0
                representative[key] = sql
                keys_in_order.append(key)
            votes[key] += 1

        # Stable sort: most votes first, ties resolved by first appearance.
        keys_in_order.sort(key=lambda k: -votes[k])

        # -- 3) execution filter: most-voted candidate that runs cleanly ------
        for key in keys_in_order:
            candidate = representative[key]
            if self._executes_cleanly(candidate):
                return candidate

        # -- 4) fallback: nothing ran cleanly, keep the plurality candidate ---
        return representative[keys_in_order[0]]