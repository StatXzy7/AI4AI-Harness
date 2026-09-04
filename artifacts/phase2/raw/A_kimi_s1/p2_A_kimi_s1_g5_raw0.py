"""Execution-feedback repair harness: generate SQL, execute it, and feed the database's errors (or empty-result notices) back into the prompt so the frozen model rewrites the query."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS1G5(SQLHarness):
    """Generate -> execute -> repair control loop for Text-to-SQL.

    The first greedy candidate is executed against the real database. On a
    failure (or a suspicious 0-row result) the database's feedback is added
    to a repair prompt and the frozen model is asked to rewrite the query.
    The loop stops as soon as a query runs and returns rows; if the attempt
    budget is exhausted, the best candidate seen (one that at least executed
    cleanly) is returned instead of the raw first generation.
    """

    MAX_ATTEMPTS = 4

    SYSTEM = (
        "You are an expert SQLite query writer. "
        "You answer questions with exactly one correct SQL query."
    )

    # ------------------------------------------------------------------ #
    # LLM helpers
    # ------------------------------------------------------------------ #
    def _ask(self, prompt, temperature=0.0):
        out = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):          # tolerate n-style returns
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    def _extract(self, text):
        sql = (bridge.extract_sql(text) or "").strip()
        if sql:
            return sql
        raw = (text or "").strip()
        # Model may have answered with bare SQL and no fences; keep it.
        if raw and ("select" in raw.lower() or raw.lower().startswith("with")):
            return raw
        return ""

    # ------------------------------------------------------------------ #
    # Prompts
    # ------------------------------------------------------------------ #
    def _initial_prompt(self, question):
        return (
            "Write one SQLite query that answers the question.\n\n"
            "Database schema:\n" + str(self.schema) + "\n\n"
            "Question: " + question + "\n\n"
            "Rules:\n"
            "- Output ONLY the SQL query: no explanation, no markdown fences.\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- Use explicit JOIN ... ON clauses when combining tables.\n"
        )

    def _repair_prompt(self, question, failed):
        history = []
        for i, (sql, fb) in enumerate(failed[-3:], start=1):
            history.append(
                "Attempt {n} SQL:\n{sql}\nDatabase feedback on attempt {n}: {fb}".format(
                    n=i, sql=sql, fb=fb
                )
            )
        return (
            "The SQL written for this question did not work. "
            "Use the database feedback below to fix it.\n\n"
            "Database schema:\n" + str(self.schema) + "\n\n"
            "Question: " + question + "\n\n"
            + "\n\n".join(history) + "\n\n"
            "Write a DIFFERENT, corrected SQLite query that answers the question.\n"
            "Output ONLY the corrected SQL query: no explanation, no markdown fences.\n"
        )

    # ------------------------------------------------------------------ #
    # Execution feedback
    # ------------------------------------------------------------------ #
    @staticmethod
    def _feedback(result):
        if result.get("ok"):
            if result.get("rows"):
                return None  # ran and returned data -> stop looping
            return (
                "The query ran without errors but returned 0 rows, so it "
                "probably does not answer the question. Re-check join keys, "
                "WHERE filters and string literals (letter case / spelling "
                "may differ from the question)."
            )
        return "Execution error: " + str(result.get("error") or "unknown error").strip()

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        failed = []            # (sql, feedback) history for the repair prompt
        empty_ok_sql = ""      # first query that executed but gave 0 rows
        last_executed = None
        sql = self._extract(self._ask(self._initial_prompt(question), temperature=0.0))
        last_sql = sql

        for attempt in range(self.MAX_ATTEMPTS):
            if sql and sql != last_executed:
                last_executed = sql
                try:
                    result = self.execute(sql)
                except Exception as exc:            # defensive
                    result = {"ok": False, "rows": [], "error": str(exc)}
                feedback = self._feedback(result)
                if feedback is None:
                    return sql                      # ran and returned rows: done
                if result.get("ok") and not empty_ok_sql:
                    empty_ok_sql = sql              # runnable: keep as fallback
                failed.append((sql, feedback))
                last_sql = sql
            elif not sql:
                failed.append((
                    "(the previous reply contained no SQL)",
                    "No SQL query was found in your previous reply. "
                    "Output only the SQL query.",
                ))

            # Regenerate with feedback; raise temperature on later repairs so
            # the frozen model can escape repeated identical failures.
            temperature = 0.0 if attempt == 0 else min(0.3 + 0.2 * (attempt - 1), 0.7)
            new_sql = self._extract(
                self._ask(self._repair_prompt(question, failed), temperature=temperature)
            )
            if new_sql:
                if new_sql.strip() == (last_executed or "").strip():
                    failed.append((
                        new_sql,
                        "You repeated the same query that already failed. "
                        "Produce a genuinely different corrected query.",
                    ))
                else:
                    sql = new_sql

        # Budget exhausted: prefer a query that at least executed cleanly.
        return empty_ok_sql or last_sql or sql or "SELECT 1"