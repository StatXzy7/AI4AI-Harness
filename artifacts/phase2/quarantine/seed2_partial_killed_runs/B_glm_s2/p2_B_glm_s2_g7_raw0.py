"""Greedy SQL generation hardened by an execution-feedback repair loop: each candidate query is run against the database and any execution error is fed back to the model for up to three corrective regenerations."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G7(SQLHarness):
    """Text-to-SQL harness that repairs its own SQL using database error feedback.

    Control flow:
      1. Ask the model for one SQL query (greedy, temperature 0).
      2. Execute the query against the real database.
      3. If it executes cleanly, return it immediately.
      4. If it errors (or no SQL could be extracted), append the failing query
         and its error message to a growing repair context and regenerate.
      5. Repeat up to MAX_ATTEMPTS total generations; a query that repeats a
         already-failed query verbatim short-circuits the loop, since
         re-executing it cannot succeed.
    """

    MAX_ATTEMPTS = 3
    MAX_ERROR_CHARS = 400

    SYSTEM = (
        "You are an expert SQL analyst. Given a database schema and a question, "
        "write exactly one SQL query that answers the question. "
        "Respond with the SQL query only, with no explanation."
    )

    def solve(self, question: str) -> str:
        question = question or ""

        failed = []      # [(sql, error)] accumulated from earlier attempts
        seen = set()     # sql strings already tried and known to fail
        best_sql = ""    # most recent non-empty candidate (best-effort answer)
        raw_text = ""    # last raw model output, used as a final fallback

        for _ in range(self.MAX_ATTEMPTS):
            prompt = self._build_prompt(question, failed)
            raw_text = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1) or ""
            sql = bridge.extract_sql(raw_text) or ""

            if not sql:
                # Nothing executable was produced; treat it as a failed attempt
                # so the repair context tells the model to emit plain SQL.
                failed.append(("", "No SQL statement could be extracted from the output."))
                continue

            if sql in seen:
                # The model repeated a query that already failed against this
                # database; executing it again is futile, so stop early.
                best_sql = sql
                break
            seen.add(sql)
            best_sql = sql

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = str(result.get("error") or "Unknown execution error.")
            failed.append((sql, error[: self.MAX_ERROR_CHARS]))

        if not best_sql:
            # No executable SQL was ever produced across all attempts; fall
            # back to the raw text of the last generation rather than "".
            return raw_text.strip()
        return best_sql

    def _build_prompt(self, question, failed):
        lines = [
            "Database schema:",
            self.schema or "(no schema provided)",
            "",
            "Question: " + question,
        ]

        if not failed:
            lines += ["", "SQL query:"]
            return "\n".join(lines)

        lines += [
            "",
            "Your previous SQL attempts failed to execute against this database:",
        ]
        for i, (sql, error) in enumerate(failed, 1):
            lines.append("Attempt %d SQL: %s" % (i, sql if sql else "(none)"))
            lines.append("Attempt %d error: %s" % (i, error))
        lines += [
            "",
            "Write a corrected SQL query for the original question that avoids "
            "every error listed above. Respond with the SQL query only.",
        ]
        return "\n".join(lines)