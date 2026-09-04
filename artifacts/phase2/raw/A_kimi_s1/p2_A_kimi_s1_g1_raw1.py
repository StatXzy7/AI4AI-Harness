"""Iterative error-feedback repair: generate SQL greedily, execute it, and feed any database error back to the LLM to regenerate a corrected query until it runs or the retry budget is exhausted."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS1G1(SQLHarness):
    """Repair-loop harness: generate -> execute -> feed error back -> regenerate.

    A single greedy generation is tried first. Every execution failure is
    turned into a repair prompt containing (schema, question, failing SQL,
    database error). Repair temperature escalates across rounds so repeated
    identical failures are escaped. The latest non-empty candidate is kept
    as a best-effort fallback.
    """

    MAX_REPAIRS = 3                          # repair prompts after the first generation
    REPAIR_TEMPS = (0.0, 0.3, 0.6)           # escalate to break out of repeat failures

    GEN_SYS = "You are a precise Text-to-SQL engine that outputs only SQL."
    REPAIR_SYS = (
        "You fix broken SQLite queries using the database error message and "
        "the schema. Output only the corrected SQL."
    )

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _first(out) -> str:
        """Normalize llm() output (str or list) to a single string."""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    def _gen_prompt(self, question: str) -> str:
        return (
            "You are an expert SQLite Text-to-SQL system.\n"
            "Write ONE correct SQLite query that answers the question.\n\n"
            f"=== DATABASE SCHEMA ===\n{self.schema}\n\n"
            f"=== QUESTION ===\n{question}\n\n"
            "Requirements:\n"
            "- Use ONLY tables and columns that appear in the schema above.\n"
            "- Output ONLY the SQL query: no prose, no markdown fences.\n"
            "- Use explicit column names and unambiguous table qualifiers.\n\n"
            "SQL:"
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            "A SQLite query written for the question below FAILED to execute.\n\n"
            f"=== DATABASE SCHEMA ===\n{self.schema}\n\n"
            f"=== QUESTION ===\n{question}\n\n"
            f"=== FAILING SQL ===\n{bad_sql or '(empty / no SQL produced)'}\n\n"
            f"=== DATABASE ERROR ===\n{error}\n\n"
            "Diagnose the failure (e.g. nonexistent or misqualified table/column "
            "names, bad quoting, syntax errors, wrong JOIN keys, ambiguous "
            "columns, type mismatches), then write ONE corrected SQLite query.\n"
            "Use ONLY schema-listed tables and columns. Output ONLY the "
            "corrected SQL: no prose, no markdown fences.\n\n"
            "Corrected SQL:"
        )

    def _run(self, sql: str) -> dict:
        """Execute defensively: a harness-level crash is treated as an error."""
        try:
            return self.execute(sql)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "rows": [], "error": f"harness exception: {exc}"}

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # ---- Step 1: one greedy generation -----------------------------
        raw = self._first(self.llm(
            self._gen_prompt(question),
            system=self.GEN_SYS,
            temperature=0.0,
            n=1,
        ))
        sql = bridge.extract_sql(raw) or ""
        best = sql

        # If the model emitted nothing extractable, skip execution and go
        # straight into the repair loop with a synthetic error signal.
        error = None if sql.strip() else "model produced no SQL"

        # ---- Step 2: execute-and-repair loop ---------------------------
        for attempt in range(self.MAX_REPAIRS + 1):
            if error is None:
                result = self._run(sql)
                if result.get("ok"):
                    return sql
                error = result.get("error") or "unknown execution error"

            if attempt == self.MAX_REPAIRS:
                break  # repair budget exhausted

            temp = self.REPAIR_TEMPS[min(attempt, len(self.REPAIR_TEMPS) - 1)]
            raw = self._first(self.llm(
                self._repair_prompt(question, sql, error),
                system=self.REPAIR_SYS,
                temperature=temp,
                n=1,
            ))
            repaired = bridge.extract_sql(raw) or ""

            if repaired.strip():
                sql, best, error = repaired, repaired, None  # execute next round
            # else: keep the old error so the next (hotter) round re-prompts
            # immediately without wasting an execution on a known-bad query.

        # ---- Step 3: best-effort fallback ------------------------------
        return best.strip() or "SELECT 1"