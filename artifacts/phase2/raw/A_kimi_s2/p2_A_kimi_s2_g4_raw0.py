"""Self-repairing Text-to-SQL harness: every generated query is executed and database error messages are fed back to the model for bounded iterative correction."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G4(SQLHarness):
    """Execution-feedback repair loop around the frozen weak solver.

    Control flow:
      1. Greedily generate an initial SQL query for the question.
      2. Execute it against the real database via self.execute.
      3. If execution succeeds, return the query immediately.
      4. If execution fails, record the (query, error) pair in a failure
         history and ask the model for a corrected query conditioned on the
         schema, the question, and the FULL history of failing queries with
         their exact database error messages.
      5. Repeat for a bounded number of repair rounds; if the budget is
         exhausted, return the most recent candidate so the caller always
         receives a SQL string.
    """

    MAX_REPAIRS = 3       # error-feedback regeneration rounds after first try
    MAX_ERROR_CHARS = 800  # keep oversized driver messages out of the prompt

    def solve(self, question: str) -> str:
        sql = self._initial_sql(question)
        failures = []  # [(sql, error), ...] for every execution that failed

        for _ in range(self.MAX_REPAIRS + 1):
            if not sql:
                # Extraction produced nothing usable; regenerate from scratch.
                sql = self._initial_sql(question)
                continue

            outcome = self.execute(sql)
            if outcome.get("ok"):
                return sql

            error = str(outcome.get("error") or "unknown execution error")
            failures.append((sql, error[: self.MAX_ERROR_CHARS]))

            if len(failures) > self.MAX_REPAIRS:
                break  # repair budget exhausted

            repaired = self._repair_sql(question, failures)
            if not repaired or repaired == sql:
                break  # model has nothing new; stop and return best effort
            sql = repaired

        if sql:
            return sql
        if failures:
            return failures[-1][0]
        return "SELECT 1"

    # ------------------------------------------------------------------
    # LLM stages
    # ------------------------------------------------------------------

    def _initial_sql(self, question: str) -> str:
        system = (
            "You are an expert SQL developer. Given a database schema and a "
            "natural-language question you write a single SQL query answering "
            "the question. You output only SQL, with no explanation."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. "
            "Output only the SQL."
        )
        return self._extract(self.llm(prompt, system=system, temperature=0.0))

    def _repair_sql(self, question: str, failures) -> str:
        blocks = []
        for idx, (bad_sql, error) in enumerate(failures, start=1):
            blocks.append(
                f"Attempt {idx} SQL:\n