"""Harness that repairs SQL through an execute-and-feedback loop: each candidate is run, and execution errors or empty results are fed back to the LLM for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G7(SQLHarness):
    """Generate -> execute -> repair loop for Text-to-SQL.

    The initial greedy candidate is executed against the database. Whenever
    execution fails (or succeeds but returns zero rows), the error/feedback is
    appended to a repair prompt and the model regenerates. Temperature is
    escalated on later rounds and on repeated outputs to escape loops. The
    last error-free query is kept as a fallback.
    """

    MAX_ATTEMPTS = 5

    SYSTEM = (
        "You are an expert SQLite text-to-SQL engine. "
        "You respond with exactly one valid SQLite SQL statement and nothing else."
    )

    def solve(self, question: str) -> str:
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SQL query that answers the question. "
            "Output only the SQL statement."
        )

        sql = bridge.extract_sql(
            self.llm(base_prompt, system=self.SYSTEM, temperature=0.0)
        )

        attempts = []        # (sql, feedback) pairs for imperfect tries
        fallback_sql = None  # most recent query that executed without error

        for attempt in range(self.MAX_ATTEMPTS):
            if not sql:
                sql = self._regenerate(base_prompt, attempts, temperature=0.7)
                if not sql:
                    break

            try:
                result = self.execute(sql)
            except Exception as exc:  # treat executor exceptions as repairable errors
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                rows = result.get("rows") or []
                if rows:
                    return sql
                fallback_sql = sql
                feedback = (
                    "The query executed successfully but returned 0 rows. "
                    "Re-check join conditions, filter values (string literals may "
                    "differ in case or spelling), and whether the correct tables "
                    "and columns were used."
                )
            else:
                feedback = (
                    "The query failed to execute. SQLite error: "
                    f"{result.get('error', 'unknown error')}. Fix the SQL."
                )

            attempts.append((sql, feedback))
            # Escalate temperature in later rounds to diversify repairs.
            sql = self._regenerate(
                base_prompt, attempts, temperature=0.0 if attempt < 2 else 0.5
            )

        return fallback_sql or sql or "SELECT 1"

    def _regenerate(self, base_prompt, attempts, temperature):
        """Ask the LLM to repair the SQL given the failure history."""
        history = "\n\n".join(
            f"Attempt {i + 1} SQL:\n{s}\nProblem observed: {fb}"
            for i, (s, fb) in enumerate(attempts[-3:])
        )
        prompt = (
            f"{base_prompt}\n\n"
            "Previous attempts and the problems they produced:\n"
            f"{history}\n\n"
            "Rewrite the SQL so it executes correctly and answers the question. "
            "Output only the corrected SQL statement."
        )
        out = bridge.extract_sql(
            self.llm(prompt, system=self.SYSTEM, temperature=temperature)
        )
        # If regeneration stalls (empty or identical to the failed query),
        # retry once with higher temperature to break the repetition.
        if not out or (attempts and out == attempts[-1][0]):
            out = bridge.extract_sql(
                self.llm(
                    prompt,
                    system=self.SYSTEM,
                    temperature=min(1.0, temperature + 0.4),
                )
            )
        return out