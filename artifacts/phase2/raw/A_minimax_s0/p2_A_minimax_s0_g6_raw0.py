"""Repair-loop Text-to-SQL harness that regenerates queries using execution error feedback."""
# MECHANISM: repair
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS0G6(SQLHarness):
    """Wrapper around a frozen weak solver that repairs SQL via execution feedback.

    Strategy:
      1. Generate an initial SQL hypothesis from the question + schema.
      2. Execute it against the live database.
      3. If execution fails OR returns zero rows, ask the LLM to repair
         the query using the schema, the previous attempt, and the
         execution feedback (error message or empty-result notice).
      4. Stop on the first executable query that returns >=1 row, or
         after a bounded number of repair attempts.

    This realises the "repair" control-flow mechanism: a single greedy
    generation is augmented with an error-driven regeneration loop.
    """

    MAX_REPAIRS = 2  # total attempts beyond the initial generation

    # ------------------------------------------------------------------ #
    # Prompt templates                                                    #
    # ------------------------------------------------------------------ #
    _REPAIR_SYSTEM = (
        "You are an expert SQL repair assistant. Given a database schema, "
        "a natural language question, a previously generated SQL query and "
        "the error message (or an 'empty result set' notice) returned by "
        "the database engine when that query was executed, produce a "
        "corrected SQL query that answers the question. "
        "Strictly output a single SQL statement -- no prose, no "
        "markdown fences, no explanations."
    )

    def solve(self, question: str) -> str:
        schema = self.schema or ""

        # ---- Stage 1: initial greedy generation ----------------------- #
        initial_prompt = self._build_initial_prompt(schema, question)
        raw = self.llm(initial_prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw) or raw.strip()
        sql = self._sanitize(sql)

        if not sql:
            return ""

        # ---- Stage 2: execute / repair loop -------------------------- #
        for attempt in range(self.MAX_REPAIRS + 1):
            result = self.execute(sql)

            # Success: executable AND returns at least one row.
            if result.get("ok") and self._has_rows(result):
                return sql

            # Build repair feedback.
            if result.get("ok"):
                feedback = (
                    "The previous query executed successfully but returned "
                    "an empty result set, so it does not answer the question."
                )
                err = ""
            else:
                feedback = "The previous query failed to execute."
                err = (result.get("error") or "").strip()

            # Out of repair budget -- return the best candidate we have.
            if attempt >= self.MAX_REPAIRS:
                return sql

            # Ask the LLM to repair the query.
            repair_prompt = self._build_repair_prompt(
                schema=schema,
                question=question,
                bad_sql=sql,
                feedback=feedback,
                error=err,
            )
            repaired_raw = self.llm(
                repair_prompt, system=self._REPAIR_SYSTEM, temperature=0.0, n=1
            )
            new_sql = bridge.extract_sql(repaired_raw) or repaired_raw.strip()
            new_sql = self._sanitize(new_sql)

            if not new_sql or new_sql.strip() == sql.strip():
                # Model produced nothing new -- stop to avoid looping.
                return sql
            sql = new_sql

        return sql

    # ------------------------------------------------------------------ #
    # Prompt builders                                                     #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_initial_prompt(schema: str, question: str) -> str:
        return (
            "You are an expert SQL generator. Given the database schema and "
            "a natural language question, output exactly one SQL statement "
            "that answers the question. Do not include explanations, "
            "markdown fences, or comments.\n\n"
            f"SCHEMA:\n{schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            "SQL:"
        )

    @staticmethod
    def _build_repair_prompt(
        schema: str, question: str, bad_sql: str, feedback: str, error: str
    ) -> str:
        parts = [
            "DATABASE SCHEMA:",
            schema,
            "",
            "QUESTION:",
            question,
            "",
            "PREVIOUS SQL:",
            bad_sql,
            "",
            "FEEDBACK:",
            feedback,
        ]
        if error:
            parts.append("")
            parts.append("ENGINE ERROR MESSAGE:")
            parts.append(error)
        parts.append("")
        parts.append(
            "Produce a corrected SQL statement that fixes the issue above. "
            "Output only the SQL, nothing else."
        )
        parts.append("\nCORRECTED SQL:")
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _sanitize(sql: str) -> str:
        """Strip markdown fences / leading prose, return a clean SQL string."""
        if not sql:
            return ""
        text = sql.strip()

        # Drop surrounding