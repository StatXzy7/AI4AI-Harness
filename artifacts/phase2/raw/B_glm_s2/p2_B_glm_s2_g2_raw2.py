"""Execution-feedback repair loop: every generated query is executed against the database and the resulting error (or empty-result) feedback is fed back into the LLM prompt for a corrective regeneration round."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G2(SQLHarness):
    """Greedy Text-to-SQL generation wrapped in an execution-driven repair loop.

    Per question:
      1. Ask the frozen solver for one SELECT statement.
      2. Execute it on the live database with ``self.execute``.
      3. Hard failure (executor error) -> repair round carrying the exact DB error.
         Soft failure (ok but 0 rows)  -> repair round carrying the empty result.
         Success (ok and >= 1 row)     -> returned immediately.
      4. A repair round re-generates with the schema, the question, and every
         (failed query, database feedback) pair so far; if the solver echoes a
         query that already failed, the loop stops early.
      5. After MAX_ATTEMPTS generations the best candidate that ever executed
         (preferring ones that returned rows) is returned, else the last
         generation.
    """

    MAX_ATTEMPTS = 3

    _SYSTEM = (
        "You are an expert SQLite analyst. Given a database schema and a natural "
        "language question, you write exactly one SQLite SELECT query that answers "
        "the question. Reply with a single SQL code block and nothing else."
    )

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        schema = str(getattr(self, "schema", "") or "").strip()
        question = (question or "").strip()

        prompt = self._initial_prompt(question, schema)
        history = []          # (failed_sql, feedback) pairs shown to repair rounds
        best_sql = None       # best candidate that executed without error
        best_has_rows = False
        last_sql = ""         # most recent non-empty generation (final fallback)

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            # --- generation ---
            text = self._generate(prompt)
            sql = self._clean(bridge.extract_sql(text))
            if sql:
                last_sql = sql

            if not sql:
                # Nothing parseable came back: treat as a repairable failure.
                feedback = (
                    "No SQL statement could be extracted from the previous answer. "
                    "Reply with a single SQL code block containing exactly one "
                    "SQLite SELECT statement."
                )
            else:
                if self._already_tried(sql, history):
                    # The solver echoed a query that already failed; more rounds
                    # would only repeat it, so stop early.
                    break

                # --- execution: the step that drives the repair loop ---
                result = self._execute(sql)

                if result["ok"]:
                    has_rows = bool(result["rows"])
                    if best_sql is None or (not best_has_rows and has_rows):
                        best_sql, best_has_rows = sql, has_rows
                    if has_rows:
                        return sql
                    # Executed cleanly but answered nothing: soft failure.
                    feedback = (
                        "The query executed without error but returned 0 rows, "
                        "while the question is expected to have an answer; a join "
                        "or filter condition is probably wrong."
                    )
                else:
                    # Hard failure: the database error text becomes repair input.
                    feedback = self._truncate(result["error"]) or (
                        "The query raised an unknown execution error."
                    )

            history.append((sql, feedback))

            if attempt == self.MAX_ATTEMPTS:
                break
            # --- repair: regenerate with execution feedback in the prompt ---
            prompt = self._repair_prompt(question, schema, history)

        if best_sql is not None:
            return best_sql
        return last_sql or "SELECT 1"

    # ------------------------------------------------------------- prompting

    def _initial_prompt(self, question: str, schema: str) -> str:
        return (
            "DATABASE SCHEMA\n"
            f"{schema or '(schema not provided)'}\n\n"
            "QUESTION\n"
            f"{question}\n\n"
            "TASK\n"
            "Write exactly one SQLite SELECT statement that answers the question above.\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Never invent table, column, or alias names.\n"
            "- Output the query inside a single SQL code block, with no explanation.\n"
        )

    def _repair_prompt(self, question: str, schema: str, history) -> str:
        lines = [
            "DATABASE SCHEMA",
            schema or "(schema not provided)",
            "",
            "QUESTION",
            question,
            "",
            "FAILED ATTEMPTS",
        ]
        for i, (bad_sql, feedback) in enumerate(history, 1):
            shown = bad_sql if bad_sql else "-- (no SQL was extracted)"
            lines.append(f"{i}. Query:\n   {shown}")
            lines.append(f"   Database feedback: {feedback}")
        lines.extend([
            "",
            "TASK",
            "The attempts above did not answer the question against this SQLite "
            "database. Using the schema, diagnose every reported problem (unknown "
            "column or table, wrong join key, type mismatch, bad aggregation, or a "
            "filter that removed every row) and output one corrected SQLite SELECT "
            "statement that differs from every failed attempt. Output only a single "
            "SQL code block containing the corrected query.",
        ])
        return "\n".join(lines)

    # ------------------------------------------------------------------- LLM

    def _generate(self, prompt: str) -> str:
        out = self.llm(prompt, system=self._SYSTEM, temperature=0.0, n=1