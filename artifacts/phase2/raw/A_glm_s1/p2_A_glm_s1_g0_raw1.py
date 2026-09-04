"""Iterative repair: each generated query is executed against the database and execution errors are fed back into the prompt for up to four corrective regeneration rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G0(SQLHarness):
    """Weak-solver wrapper that adds an execution-feedback repair loop.

    Control flow per question:
      1. Ask the frozen solver for one SQL query (greedy, single call).
      2. Guard: only a single read-only SELECT / WITH...SELECT statement is
         ever handed to the executor.
      3. Execute the candidate on the real database via self.execute().
      4. If it runs cleanly, return it immediately (first success wins).
      5. If it fails, append (query, engine error) to a feedback history,
         rebuild the prompt containing that history, and regenerate.
    After MAX_ROUNDS attempts the most recent non-empty candidate is
    returned as a last resort (it saw the most feedback).
    """

    MAX_ROUNDS = 4
    MAX_HISTORY = 3

    SYSTEM = (
        "You are an expert SQLite programmer. You reply with exactly one "
        "read-only SQL SELECT query and no explanation."
    )

    def solve(self, question: str) -> str:
        self.last_trace = []
        history = []
        fallback_sql = ""

        for round_no in range(self.MAX_ROUNDS):
            prompt = self._build_prompt(question, history)

            raw = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""
            sql = bridge.extract_sql(raw or "").strip()

            if not sql:
                self._record(
                    history, round_no, "",
                    "no SQL statement could be extracted from the model output",
                )
                continue

            fallback_sql = sql

            guard_error = self._guard(sql)
            if guard_error is not None:
                self._record(history, round_no, sql, guard_error)
                continue

            result = self._safe_execute(sql)
            if result.get("ok"):
                self.last_trace.append(
                    {
                        "round": round_no,
                        "sql": sql,
                        "ok": True,
                        "rows": len(result.get("rows") or []),
                    }
                )
                return sql  # first query that executes cleanly wins

            error = (result.get("error") or "unknown execution error").strip()
            self._record(history, round_no, sql, error)

        # Nothing ever executed cleanly: return the last (most-informed) candidate.
        return fallback_sql

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _record(self, history, round_no, sql, error):
        """Store a failed attempt both for the next prompt and for the trace."""
        history.append({"sql": sql, "error": error})
        self.last_trace.append({"round": round_no, "sql": sql, "ok": False, "error": error})

    @staticmethod
    def _guard(sql):
        """Reject anything that is not one read-only SELECT/WITH statement."""
        lowered = sql.lstrip().lower()
        if not lowered.startswith(("select", "with")):
            return "rejected: only a single read-only SELECT (or WITH ... SELECT) statement may be executed"
        body = sql.strip().rstrip(";").strip()
        if ";" in body:
            return "rejected: output must be exactly one SQL statement (stray ';' found)"
        return None

    def _safe_execute(self, sql):
        """Never let an executor crash kill the repair loop."""
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": "executor raised: %s" % exc}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "executor returned a malformed result"}
        return result

    def _build_prompt(self, question, history):
        lines = [
            "Database schema (SQLite):",
            self.schema,
            "",
            "Task: write ONE SQL query that answers the question below.",
            "",
            "Question: %s" % question,
            "",
            "Rules:",
            "- Output exactly one read-only SELECT (or WITH ... SELECT) statement.",
            "- Use only tables and columns that appear in the schema.",
            "- Quote string literals with single quotes.",
            "- Put the final query in a