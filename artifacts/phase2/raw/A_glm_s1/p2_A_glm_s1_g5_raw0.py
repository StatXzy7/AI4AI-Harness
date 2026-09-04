"""Repair loop: generate SQL greedily, execute it, and iteratively regenerate the query by feeding every execution error back into the prompt until it executes cleanly or a bounded repair budget is exhausted."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G5(SQLHarness):
    """Execution-feedback repair wrapped around the frozen weak solver.

    Control flow (a real change vs. a single greedy call):

      1. Ask the solver for one SQL statement (temperature 0).
      2. Execute the statement against the live database.
      3. If the database rejects it, record the exact error together with the
         offending SQL and re-ask the solver, showing it *all* accumulated
         failures so it does not repeat them.
      4. Repeat up to ``MAX_REPAIR_ROUNDS`` corrective rounds; return the
         first query that executes, or the last one produced as a fallback.

    Read-only guardrails (exactly one SELECT / WITH ... SELECT statement) are
    enforced before anything touches the database, and violations travel back
    through the same repair channel as genuine database errors.  A loop guard
    breaks out early if the solver regenerates an already-failed query
    verbatim.
    """

    MAX_REPAIR_ROUNDS = 3

    SYSTEM_PROMPT = (
        "You are an expert SQL analyst. Given a database schema and a question, "
        "write exactly one read-only SQL SELECT statement that answers the "
        "question. Use only the tables and columns that appear in the schema. "
        "Output the SQL statement and nothing else."
    )

    #: filled in by solve() -- tuple of (sql, error) pairs, for inspection
    last_repair_history = ()

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        failures = []   # the model's error memory: [(sql, error), ...]
        tried = set()   # loop guard: every SQL string already attempted
        last_sql = ""   # best-effort answer if nothing ever executes

        prompt = self._first_prompt(question)
        for _ in range(1 + self.MAX_REPAIR_ROUNDS):
            raw = self._generate(prompt)
            sql = self._clean(bridge.extract_sql(raw))

            if sql in tried:
                # The solver repeated an already-failed query verbatim;
                # another round with the same information cannot help.
                break
            tried.add(sql)
            if sql:
                last_sql = sql

            error = self._validate_and_run(sql)
            if error is None:  # the query executed cleanly
                self.last_repair_history = tuple(failures)
                return sql

            failures.append((sql, error))
            prompt = self._repair_prompt(question, failures)

        self.last_repair_history = tuple(failures)
        return last_sql

    # ------------------------------------------------------------------ #
    # prompt construction
    # ------------------------------------------------------------------ #

    def _first_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "%s\n\n"
            "Question: %s\n\n"
            "Write the SQL query now." % (self.schema, question)
        )

    def _repair_prompt(self, question: str, failures) -> str:
        lines = [
            "Database schema:",
            self.schema,
            "",
            "Question: %s" % question,
            "",
            "Your previous SQL attempts failed. Each attempt is listed with "
            "the exact error the database returned:",
            "",
        ]
        for i, (sql, error) in enumerate(failures, 1):
            lines.append("Attempt %d:" % i)
            lines.append("  SQL: %s" % (sql if sql else "(no SQL found)"))
            lines.append("  Error: %s" % error)
            lines.append("")
        lines.append(
            "Write ONE corrected SQL SELECT statement that answers the "
            "question and avoids every error listed above. Output the SQL "
            "statement and nothing else."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _validate_and_run(self, sql: str):
        """Execute ``sql``; return None on success, else an error message."""
        if not sql:
            return (
                "No SQL statement could be extracted from the reply. Respond "
                "with a single SQL SELECT statement and nothing else."
            )
        if not self._is_single_select(sql):
            return (
                "The statement was rejected: exactly one read-only SELECT (or "
                "WITH ... SELECT) query is allowed. Rewrite it as such."
            )
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: keep the repair loop alive
            return "Executing the query raised an exception: %s" % exc
        if not isinstance(result, dict):
            return "Executing the query returned an unexpected result."
        if result.get("ok"):
            return None
        err = (result.get("error") or "").strip()
        return err or "The query failed to execute (no error message was provided)."

    @staticmethod
    def _is_single_select(sql: str) -> bool:
        body = sql.strip()
        if not body or ";" in body:
            return False
        stripped = body.lstrip("(")
        if not stripped:
            return False
        head = stripped.split(None, 1)[0].upper()
        return head in ("SELECT", "WITH")

    @staticmethod
    def _clean(sql) -> str:
        if not sql:
            return ""
        sql = sql.strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    def _generate(self, prompt: str) -> str:
        text = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        return "" if text is None else str(text)