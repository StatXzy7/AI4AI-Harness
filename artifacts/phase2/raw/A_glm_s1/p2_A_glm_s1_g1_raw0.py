"""Greedy text-to-SQL generation hardened by an execution-feedback repair loop: each candidate query is executed against the database and, when it fails, the failing SQL plus the real database error is fed back to the solver for a bounded number of correction rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G1(SQLHarness):
    """One greedy generation, then execution-driven repair.

    Control flow (a real change versus a single generation call):

    1. Ask the frozen solver once, greedily (temperature 0), for a SQL query.
    2. Execute that query with ``self.execute``.
    3. If the query fails -- an execution error, or not even a SELECT --
       build a repair prompt containing the schema, the question, the failing
       SQL and the exact database error message, and let the solver
       regenerate a corrected query.
    4. Repeat steps 2-3 at most ``MAX_REPAIRS`` times.
    5. Return the first query that executes cleanly; if none does, return the
       most recent attempt.
    """

    MAX_REPAIRS = 2      # extra solver calls allowed after a failure
    MAX_HISTORY = 3      # failed attempts echoed back into the repair prompt
    SYSTEM = (
        "You are a precise text-to-SQL engine. Given a database schema and a "
        "question, you write exactly one SQLite SELECT statement that answers "
        "the question."
    )

    # ------------------------------------------------------------------ LLM

    def _generate(self, prompt):
        """One greedy call to the frozen solver; robust to return shapes."""
        try:
            out = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        except TypeError:                    # older positional-only LLM API
            out = self.llm(prompt)
        if isinstance(out, (list, tuple)):   # n=1 may still come back as a list
            out = out[0] if out else ""
        if out is None:
            return ""
        return out if isinstance(out, str) else str(out)

    # ------------------------------------------------------------- checking

    def _run_sql(self, sql):
        """Execute *sql* defensively; never raise, always (ok, error)."""
        try:
            res = self.execute(sql)
        except Exception as exc:             # the DB layer must never kill us
            return False, "execution crashed: %s: %s" % (type(exc).__name__, exc)
        if not isinstance(res, dict):
            return False, "execution returned a non-dictionary result"
        if res.get("ok"):
            return True, ""
        err = res.get("error") or "execution failed (no error message)"
        return False, str(err)[:500]

    def _evaluate(self, sql):
        """Shape-check first (never run non-SELECT SQL), then execute."""
        text = (sql or "").strip()
        if not text:
            return False, "no SQL was produced"
        body = text.lstrip("(").rstrip(";").strip()
        first = body.split(None, 1)[0].lower() if body else ""
        if first not in ("select", "with") and not text.startswith("("):
            return False, ("query is not a SELECT statement (starts with %r); "
                           "only a single SELECT query is allowed" % first)
        return self._run_sql(text)

    # -------------------------------------------------------------- prompts

    def _initial_prompt(self, question):
        return "\n".join([
            "Database schema:",
            self.schema or "(no schema provided)",
            "",
            "Question: %s" % question,
            "",
            "Write one SQL SELECT query that answers the question.",
            "Rules:",
            "- Use only tables and columns that appear in the schema.",
            "- Use valid SQLite syntax.",
            "- Answer with a single