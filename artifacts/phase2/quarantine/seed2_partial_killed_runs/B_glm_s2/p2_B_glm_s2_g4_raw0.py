"""Iterative execution-feedback repair: greedily generate a SQL candidate, execute it against the database, and feed the error (or an empty result set) back to the model for up to MAX_ATTEMPTS corrected regenerations."""

from ..harness_base import SQLHarness
from .. import bridge

# MECHANISM: repair


class P2P2BGlmS2G4(SQLHarness):
    """Greedy text-to-SQL generation refined by an execution-repair loop.

    Control flow:
      1. Ask the frozen solver for one SQL query (temperature 0).
      2. Execute the query on the real database.
      3. If it errors, append the SQL + database error to a repair history and
         re-ask the model to fix it.
      4. If it runs but returns 0 rows, keep it as a safe fallback but still
         ask for one more correction (empty results often mean a wrong join
         or filter).
      5. Return the first query that executes and returns rows; otherwise the
         first query that executed at all; otherwise the last model output.
    """

    MAX_ATTEMPTS = 4          # total LLM calls (1 initial + up to 3 repairs)
    FALLBACK_SQL = "SELECT 1" # always-executable last resort

    SYSTEM = (
        "You are an expert text-to-SQL translator. You are given a database "
        "schema and a natural language question. Output exactly one SQLite "
        "query that answers the question. Respond with the SQL query only: "
        "no explanation, no markdown, no code fences."
    )

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _generate(self, prompt: str) -> str:
        """One greedy LLM call, normalized to a plain string."""
        try:
            out = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        except Exception as exc:  # defensive: keep the loop alive
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if not isinstance(out, str):
            out = str(out)
        return out

    @staticmethod
    def _normalize(sql: str) -> str:
        sql = (sql or "").strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    def _run(self, sql: str) -> dict:
        """Execute defensively; never let an executor crash kill the loop."""
        try:
            result = self.execute(sql)
        except Exception as exc:
            result = {"ok": False, "rows": [], "error": "executor raised: %r" % (exc,)}
        if not isinstance(result, dict):
            result = {"ok": False, "rows": [], "error": "executor returned no result"}
        return result

    def _build_prompt(self, question: str, history: list) -> str:
        parts = [
            "Database schema:",
            (self.schema or "").strip(),
            "",
            "Question: " + (question or "").strip(),
        ]
        if not history:
            parts.append("")
            parts.append("Write the SQL query that answers the question.")
        else:
            parts.append("")
            parts.append(
                "Your previous attempts were executed on the database and "
                "produced the following feedback:"
            )
            for idx, entry in enumerate(history, 1):
                parts.append(
                    "Attempt %d SQL: %s" % (idx, entry["sql"] or "(no SQL found)")
                )
                parts.append("Attempt %d feedback: %s" % (idx, entry["feedback"]))
            parts.append("")
            parts.append(
                "Using that feedback, write a corrected SQL query that answers "
                "the question. Output the SQL query only."
            )
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        history = []      # repair history fed back into the prompt
        seen = {}         # sql -> cached execution result (dedup / stuck guard)
        best_sql = None   # first query that executed successfully
        last_sql = ""     # most recent normalized model output

        for _ in range(self.MAX_ATTEMPTS):
            prompt = self._build_prompt(question, history)
            raw = self._generate(prompt)
            sql = self._normalize(bridge.extract_sql(raw))
            last_sql = sql

            # No SQL could be extracted: ask again, more forcefully.
            if not sql:
                history.append({
                    "sql": "",
                    "feedback": (
                        "No SQL statement could be extracted from the reply. "
                        "Reply with a single SQL query and nothing else."
                    ),
                })
                continue

            # Greedy decoding is repeating a query we already tried; its
            # outcome is known, so further attempts are pointless.
            if sql in seen:
                break

            result = self._run(sql)
            seen[sql] = result
            rows = result.get("rows") or []
            error = result.get("error") or "unknown execution error"

            if result.get("ok"):
                if best_sql is None:
                    best_sql = sql  # safe fallback: it at least executes
                if rows:
                    # Executes AND returns data: accept immediately.
                    return sql
                # Executes but empty: plausible-but-suspicious; try to repair.
                history.append({
                    "sql": sql,
                    "feedback": (
                        "The query executed without error but returned 0 rows, "
                        "which suggests it does not actually answer the "
                        "question. Rewrite it (check joins, filters, and "
                        "column names)."
                    ),
                })
            else:
                # Hard failure: the error message is the repair signal.
                history.append({
                    "sql": sql,
                    "feedback": (
                        "The query failed to execute. Database error: %s "
                        "Rewrite the query to fix this." % error
                    ),
                })

        if best_sql is not None:
            return best_sql
        return last_sql if last_sql else self.FALLBACK_SQL