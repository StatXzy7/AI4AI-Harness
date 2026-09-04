"""Self-debugging Text-to-SQL harness that executes each candidate query and feeds real execution feedback (errors, or a suspicious empty result) back to the frozen solver for iterative repair."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G6(SQLHarness):
    """Generate SQL greedily, execute it, and repair it in a closed loop.

    Instead of trusting a single greedy decode, every candidate query is run
    against the database. Hard failures (syntax errors, unknown columns, bad
    types) and one class of soft failure (a query that runs but returns zero
    rows) are converted into natural-language feedback and appended to the
    prompt, so the frozen solver can diagnose and correct its own mistake on
    the next attempt. The loop is bounded, caches executions, and always
    returns the best available query.
    """

    MAX_ATTEMPTS = 5      # 1 initial generation + up to 4 repair rounds
    MAX_HISTORY = 3       # how many past failures are shown to the solver
    MAX_SOFT_REPAIRS = 1  # at most one "empty result, please verify" round

    def solve(self, question: str) -> str:
        system_prompt = (
            "You are an expert Text-to-SQL engine. Given a database schema and "
            "a natural-language question, you write exactly one correct, "
            "executable SQL query. You output only SQL: no prose, no markdown "
            "fences, no commentary."
        )
        base_prompt = self._build_base_prompt(question)

        failures = []            # list of (sql_or_text, feedback) pairs
        cache = {}               # sql -> execution outcome (avoids re-running)
        soft_repairs = 0
        last_ok_empty = None     # last query that ran cleanly but gave 0 rows
        last_sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            prompt = self._build_prompt(base_prompt, failures)
            # Greedy for the first shot and the first repair; a little
            # exploration afterwards to escape identical repeats.
            temperature = 0.0 if attempt <= 1 else 0.4

            text = self._call_llm(prompt, system_prompt, temperature)
            sql = self._to_sql(text)

            if not sql:
                failures.append((
                    (text or "")[:400],
                    "The response contained no parseable SQL query.",
                ))
                continue
            last_sql = sql

            outcome = cache.get(sql)
            if outcome is None:
                outcome = self._safe_execute(sql)
                cache[sql] = outcome

            if outcome["ok"]:
                if outcome["rows"]:
                    return sql  # executed and produced rows: accept

                # Soft failure: empty result sets are often caused by a wrong
                # literal or join, but they can also be genuinely correct, so
                # we ask the solver to verify exactly once.
                if soft_repairs < self.MAX_SOFT_REPAIRS:
                    soft_repairs += 1
                    last_ok_empty = sql
                    failures.append((
                        sql,
                        "The query executed without error but returned 0 rows. "
                        "Re-check string literals (exact case, whitespace, "
                        "quoting), join keys, and WHERE conditions against the "
                        "schema and the question. If an empty answer is truly "
                        "correct, return the same query again.",
                    ))
                    continue
                return sql

            # Hard failure: feed the database's own error message back.
            failures.append((
                sql,
                "The database rejected this query with the following error: "
                f"{outcome['error']}",
            ))

        # Fallbacks: prefer a query that at least executed cleanly.
        if last_ok_empty is not None:
            return last_ok_empty
        if last_sql:
            return last_sql
        if failures:
            return failures[-1][0]
        return "SELECT 1"

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _build_base_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question.\n"
            "Rules:\n"
            "- Use only tables and columns that exist in the schema, spelled "
            "exactly as shown.\n"
            "- Qualify columns with their table name when joining tables.\n"
            "- Match string literals to the exact values implied by the "
            "question.\n"
            "- Do not invent tables, columns, or values.\n"
            "- Output only the SQL query."
        )

    def _build_prompt(self, base_prompt: str, failures) -> str:
        if not failures:
            return base_prompt
        parts = [
            base_prompt,
            "",
            "Previous attempts and the feedback obtained by actually running "
            "them on the database:",
        ]
        for i, (sql, feedback) in enumerate(failures[-self.MAX_HISTORY:], 1):
            parts.append(f"--- Attempt {i} ---\n{sql}\nFeedback: {feedback}")
        parts.append(
            "Diagnose exactly why these attempts failed and produce a "
            "corrected single SQL query that avoids repeating them. Output "
            "only the corrected SQL."
        )
        return "\n\n".join(parts)

    def _call_llm(self, prompt: str, system: str, temperature: float) -> str:
        resp = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(resp, (list, tuple)):
            return resp[0] if resp else ""
        return resp if isinstance(resp, str) else str(resp)

    def _safe_execute(self, sql: str) -> dict:
        try:
            outcome = self.execute(sql)
        except Exception as exc:  # defensive: treat harness errors as DB errors
            outcome = {"ok": False, "rows": [], "error": f"execution raised: {exc}"}
        ok = bool(outcome.get("ok")) if isinstance(outcome, dict) else False
        rows = outcome.get("rows") if isinstance(outcome, dict) else []
        error = outcome.get("error") if isinstance(outcome, dict) else "unknown"
        return {"ok": ok, "rows": rows or [], "error": str(error or "unknown")[:600]}

    def _to_sql(self, text: str) -> str:
        if not text:
            return ""
        sql = ""
        try:
            sql = bridge.extract_sql(text) or ""
        except Exception:
            sql = ""
        if not sql:
            sql = self._strip_fences(text)
        sql = sql.strip()
        if sql.endswith(";"):
            sql = sql[:-1].strip()
        return sql

    @staticmethod
    def _strip_fences(text: str) -> str:
        t = text.strip()
        if t.startswith("