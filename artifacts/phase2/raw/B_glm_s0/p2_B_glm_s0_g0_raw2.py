"""Execute-verified repair loop: the candidate SQL is run against the database and any resulting engine error is fed back to the model for up to three corrective regeneration rounds."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G0(SQLHarness):
    """Greedy Text-to-SQL generation hardened by execution-error repair.

    Control flow (a real loop, not merely a longer prompt):

      1. One greedy LLM call maps (schema, question) -> candidate SQL.
      2. The candidate is shape-checked (read-only SELECT/WITH) and then
         executed against the real database via ``self.execute``.
      3. On failure, the exact engine error message, the offending SQL, the
         schema and the question are packed into a repair prompt and a fresh
         greedy call regenerates the query.
      4. Steps 2-3 repeat until the query executes cleanly, the repair budget
         (``MAX_REPAIRS``) is exhausted, or the model stops producing novel
         candidates (the loop never spins on a repeated query).

    The last candidate is always returned, so the caller receives a
    best-effort answer even when every round fails.
    """

    MAX_REPAIRS = 3
    READONLY_HEADS = ("select", "with")

    SYSTEM = (
        "You are an expert Text-to-SQL engine. "
        "Reply with exactly one read-only SQL query and nothing else."
    )

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        """Answer ``question`` with a SQL string, repairing on execution errors."""
        sql = self._extract(self._ask(self._first_prompt(question)))

        seen = {sql.casefold()} if sql else set()

        # Rounds 0 .. MAX_REPAIRS-1 may trigger a repair call; the final round
        # only validates the last candidate, so every returned query has been
        # executed (or at least shape-checked) exactly once.
        for round_index in range(self.MAX_REPAIRS + 1):
            ok, error = self._validate_and_run(sql)
            if ok:
                return sql
            if round_index == self.MAX_REPAIRS:
                break  # repair budget spent

            fixed = self._extract(
                self._ask(self._repair_prompt(question, sql, error, round_index))
            )
            if not fixed or fixed.casefold() in seen:
                break  # no new signal: further calls would just loop
            seen.add(fixed.casefold())
            sql = fixed

        return sql

    # -------------------------------------------------------- LLM plumbing

    def _ask(self, prompt: str) -> str:
        """One greedy LLM call; tolerates backends that return a 1-item list."""
        text = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        return text if isinstance(text, str) else str(text)

    def _extract(self, text: str) -> str:
        """Pull a single SQL statement out of a model reply and normalise it."""
        sql = ""
        if text:
            try:
                sql = bridge.extract_sql(text) or ""
            except Exception:
                sql = ""
            if not sql:
                sql = self._scan_for_query(text)
        return self._tidy(sql)

    @staticmethod
    def _scan_for_query(text: str) -> str:
        """Fallback extraction: first line that plainly starts a query."""
        for line in text.splitlines():
            stripped = line.strip().strip("`").rstrip(";").strip()
            if stripped.casefold().startswith(("select", "with")):
                return stripped
        return ""

    @staticmethod
    def _tidy(sql: str) -> str:
        """Strip surrounding whitespace and any trailing semicolons."""
        sql = (sql or "").strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    # --------------------------------------------------- validate & execute

    def _validate_and_run(self, sql: str):
        """Return ``(ok, error_message)`` for a candidate query."""
        if not sql:
            return False, "no SQL statement was found in the model reply"

        head = sql.lstrip().split(None, 1)[0].lower()
        if head not in self.READONLY_HEADS:
            return False, (
                "the statement must be a read-only query starting with "
                "SELECT or WITH (it started with %r)" % head
            )

        try:
            result = self.execute(sql)
        except Exception as exc:  # engine crash, not a SQL-level error
            return False, "execution raised %s: %s" % (type(exc).__name__, exc)

        if not isinstance(result, dict):
            return False, "execution returned an unexpected non-dict result"
        if result.get("ok"):
            return True, ""

        err = result.get("error")
        return False, str(err) if err else "unknown execution error"

    # -------------------------------------------------------------- prompts

    def _first_prompt(self, question: str) -> str:
        return (
            "Database schema:\n%s\n\n"
            "Question: %s\n\n"
            "Task: write ONE SQL query that answers the question.\n"
            "Rules:\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- The query must be read-only (start with SELECT or WITH).\n"
            "- Emit the query alone inside a