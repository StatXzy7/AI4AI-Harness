"""Execute-and-repair loop: the greedily generated SQL is run against the database, and any execution error (plus the history of failed attempts) is fed back to the LLM for up to three corrective regenerations."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G0(SQLHarness):
    """Text-to-SQL harness that improves on a single greedy generation with an
    execute-and-repair control loop.

    Flow (a genuine control-flow change vs. one greedy call):

      1. One greedy generation produces an initial SQL candidate from the
         schema + question.
      2. The candidate is executed on the target database via ``self.execute``.
      3. If execution fails, the failing SQL together with the database error
         message -- plus the full history of earlier failed attempts -- is fed
         back into a repair prompt, and the LLM regenerates a corrected query.
         Exact duplicates of already-failed queries are detected and rejected
         without wasting an execution, with an explicit nudge to change course.
      4. Steps 2-3 repeat until a query executes cleanly or the attempt budget
         (``MAX_ATTEMPTS`` generations in total) is exhausted.
      5. The most recent candidate is returned as the best-effort answer even
         if it never executed cleanly.
    """

    MAX_ATTEMPTS = 4  # 1 initial generation + up to 3 error-feedback repairs
    SYSTEM = (
        "You are a careful text-to-SQL translator. "
        "Reply with exactly one SQL query and nothing else."
    )

    def solve(self, question: str) -> str:
        attempts = []   # history of (sql, error) pairs for failed attempts
        tried = set()   # normalized text of queries already sent to the DB
        last_sql = ""

        for i in range(self.MAX_ATTEMPTS):
            if i == 0:
                prompt = self._initial_prompt(question)
            else:
                prompt = self._repair_prompt(question, attempts)

            text = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1) or ""
            sql = self._clean(bridge.extract_sql(text))

            if not sql:
                attempts.append(
                    ("", "No SQL statement could be extracted from the response.")
                )
                continue

            last_sql = sql

            key = " ".join(sql.split()).lower()
            if key in tried:
                # The model repeated a query that already failed; skip the
                # redundant execution and push back harder next round.
                attempts.append(
                    (
                        sql,
                        "This exact query was already attempted and failed with the "
                        "error shown above; it is still invalid. Write a materially "
                        "different query.",
                    )
                )
                continue
            tried.add(key)

            result = self._run(sql)
            if result.get("ok"):
                return sql

            attempts.append(
                (sql, result.get("error") or "Unknown execution error.")
            )

        # Budget exhausted: return the best candidate we ever produced.
        return last_sql

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _run(self, sql):
        """Execute ``sql`` defensively; always return a result dict."""
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: executor itself blew up
            return {"ok": False, "rows": [], "error": "executor raised: %s" % exc}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "executor returned no result"}
        return result

    @staticmethod
    def _clean(sql):
        if not sql:
            return ""
        return sql.strip().rstrip(";").strip()

    def _schema_text(self):
        return (getattr(self, "schema", "") or "").strip() or "(no schema provided)"

    def _initial_prompt(self, question):
        return (
            "Database schema:\n%s\n\n"
            "Question: %s\n\n"
            "Write one SQL query that answers the question."
            % (self._schema_text(), question)
        )

    def _repair_prompt(self, question, attempts):
        history = "\n\n".join(
            "Attempt %d:\nSQL: %s\nError: %s"
            % (j + 1, sql if sql else "(no SQL produced)", err)
            for j, (sql, err) in enumerate(attempts)
        )
        return (
            "Database schema:\n%s\n\n"
            "Question: %s\n\n"
            "Your previous SQL attempts all failed to execute against this "
            "database:\n\n%s\n\n"
            "Using the exact error messages above, write one corrected SQL query "
            "that answers the question. Do not repeat any previously attempted "
            "query."
            % (self._schema_text(), question, history)
        )