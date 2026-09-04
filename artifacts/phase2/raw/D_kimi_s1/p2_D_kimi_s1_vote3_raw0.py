"""Harness that samples 3 independent SQL attempts from the frozen solver (n=3, temperature=0.7), executes every candidate that parses, and returns the SQL whose execution result wins the majority vote."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1Vote3(SQLHarness):
    """Self-consistency (majority-vote) harness over a frozen weak Text-to-SQL solver.

    Mechanism implemented in control flow:
      1. Query the solver once with n=3 at temperature=0.7 to obtain three
         independent SQL attempts.
      2. Extract SQL from each attempt; every candidate that parses is
         executed against the database.
      3. Group successful executions by their result set and return the
         candidate SQL belonging to the largest group (the majority result).
    """

    def solve(self, question: str) -> str:
        prompt = (
            "You are given the following database schema:\n"
            f"{self.schema}\n\n"
            "Write a single SQL query that answers the question below. "
            "Return only the SQL query, with no explanation.\n\n"
            f"Question: {question}\n"
            "SQL:"
        )
        system = "You are an expert Text-to-SQL assistant. Output only SQL."

        # --- Step 1: three independent attempts from the frozen solver ---
        response = self.llm(prompt, system=system, temperature=0.7, n=3)
        if isinstance(response, str):
            completions = [response]
        else:
            completions = list(response) if response else []

        # --- Step 2: extract SQL; keep every candidate that parses ---
        candidates = []
        for text in completions:
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                candidates.append(sql.strip())

        if not candidates:
            # Nothing parsed: last-resort passthrough of the raw first attempt.
            return completions[0] if completions else ""

        # --- Step 3: execute all parseable candidates and vote on results ---
        # result_key -> {"count": <num attempts producing it>, "sql": <a candidate>}
        result_groups = {}
        for sql in candidates:
            outcome = self.execute(sql)
            if not outcome.get("ok"):
                # Failed executions carry no result and do not vote.
                continue
            key = self._result_key(outcome.get("rows"))
            if key in result_groups:
                result_groups[key]["count"] += 1
            else:
                result_groups[key] = {"count": 1, "sql": sql}

        if result_groups:
            # Majority (plurality) winner; ties resolve to the earliest candidate.
            winner = max(result_groups.values(), key=lambda g: g["count"])
            return winner["sql"]

        # No candidate executed successfully: fall back to the first parsed SQL.
        return candidates[0]

    @staticmethod
    def _result_key(rows) -> str:
        """Canonical, hashable fingerprint of a result set (order-insensitive)."""
        if rows is None:
            return "<no-rows>"
        try:
            normalized = []
            for row in rows:
                if isinstance(row, dict):
                    normalized.append(repr(sorted(row.items())))
                elif isinstance(row, (list, tuple)):
                    normalized.append(repr(tuple(row)))
                else:
                    normalized.append(repr(row))
            return "|".join(sorted(normalized))
        except Exception:
            return repr(rows)