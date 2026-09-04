"""Weak-solver harness: generate a SQLite query, execute it, and if execution fails feed the exact SQLite error message back to the LLM and regenerate, for up to two repair rounds."""


from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS2Repair(SQLHarness):
    """Generate -> execute -> repair-with-exact-error loop (max 2 repairs).

    The repair behaviour lives in the control flow, not just the prompt:
    every generated query is really executed via ``self.execute``; when that
    fails, the *exact* runtime SQLite error string is interpolated into the
    next prompt and the query is regenerated, at most ``max_repairs`` times.
    The first query that executes successfully is returned; if all attempts
    fail, the most recent SQL produced is returned as a best effort.
    """

    #: Number of error-feedback regeneration rounds after the initial call.
    max_repairs = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. Given a database schema and a "
        "natural-language question, write exactly one SQLite query that answers "
        "the question. Respond with the SQL query only: no explanation, no "
        "markdown, no code fences."
    )

    def solve(self, question: str) -> str:
        base_prompt = (
            "Database schema (SQLite DDL):\n"
            "{schema}\n\n"
            "Question: {question}\n\n"
            "Write a single SQLite query that answers the question. Respond "
            "with the SQL query only."
        ).format(schema=self.schema, question=question)

        sql = ""
        error = ""
        last_nonempty_sql = ""

        # One initial generation plus up to `max_repairs` (2) regenerations.
        for round_index in range(1 + self.max_repairs):
            if round_index == 0:
                prompt = base_prompt
            else:
                # Repair round: replay schema + question, the previous query,
                # and the EXACT SQLite error produced by self.execute().
                prompt = (
                    "{base}\n\n"
                    "Your previous query was:\n"
                    "{sql}\n\n"
                    "Executing that query against the database FAILED with "
                    "this exact SQLite error:\n"
                    "{error}\n\n"
                    "Using the exact error message above, rewrite the query so "
                    "that it executes successfully against the schema and still "
                    "answers the question. Respond with the SQL query only."
                ).format(base=base_prompt, sql=sql, error=error)

            raw = self.llm(prompt, system=self.SYSTEM_PROMPT,
                           temperature=0.0, n=1)
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""

            sql = bridge.extract_sql(raw).strip()

            if not sql:
                # Unparseable output counts as a failed attempt; retry.
                error = ("no SQL statement could be extracted from the "
                         "model response")
                continue

            last_nonempty_sql = sql

            try:
                result = self.execute(sql)
            except Exception as exc:  # Defensive: any raise is a failure.
                result = {"ok": False, "rows": [], "error": str(exc)}

            if result.get("ok"):
                return sql  # First query that actually executed.

            # Carry the exact runtime error into the next round's prompt.
            error = str(result.get("error") or "unknown SQLite execution error")

        # All attempts exhausted: return the best SQL we have.
        return sql if sql else last_nonempty_sql