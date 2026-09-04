"""Execution-feedback repair loop: generate SQL, execute it, and feed database errors (or empty results) back for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G6(SQLHarness):
    """Text-to-SQL harness that repairs its own SQL via execution feedback.

    Instead of trusting a single greedy generation, this harness executes the
    candidate query and, on failure (a database error or a suspicious empty
    result set), sends the failing SQL plus the database feedback back to the
    frozen LLM and asks for a corrected query. The loop runs for a bounded
    number of rounds and always returns a best-effort SQL string.
    """

    SYSTEM = (
        "You are an expert SQLite text-to-SQL translator. "
        "Respond with only the SQL query, no prose, no markdown."
    )
    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        # Round 0: greedy initial generation.
        raw = self.llm(self._initial_prompt(question), system=self.SYSTEM, temperature=0.0)
        sql = bridge.extract_sql(raw) or raw.strip()

        best_valid = None  # most recent query that executed without error
        feedback = ""

        for _ in range(self.MAX_ATTEMPTS):
            if not sql:
                break

            result = self.execute(sql)

            if result.get("ok"):
                best_valid = sql
                if result.get("rows"):
                    # Executed and produced rows: accept immediately.
                    return sql
                feedback = (
                    "The query executed without errors but returned ZERO rows. "
                    "It is probably too restrictive (wrong filters, wrong joins, "
                    "wrong values, or wrong column choices). Loosen or correct it "
                    "so it actually answers the question."
                )
            else:
                feedback = (
                    "The query failed to execute. Database error message: "
                    + (result.get("error") or "unknown error")
                )

            # Repair round: feed the failing SQL and the DB feedback back in.
            raw = self.llm(
                self._repair_prompt(question, sql, feedback),
                system=self.SYSTEM,
                temperature=0.0,
            )
            sql = bridge.extract_sql(raw) or raw.strip()

        # Out of attempts: prefer the last query that at least ran cleanly,
        # otherwise return whatever the model last produced (best effort).
        return best_valid if best_valid is not None else sql

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            "Write ONE valid SQLite query that answers the following question.\n"
            "Use only tables and columns present in the schema. "
            "Return only the SQL query.\n\n"
            f"Question: {question}"
        )

    def _repair_prompt(self, question: str, bad_sql: str, feedback: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "A previous attempt generated this SQL query:\n"
            f"{bad_sql}\n\n"
            f"Execution feedback from the database:\n{feedback}\n\n"
            "Rewrite the query so it executes correctly and answers the question. "
            "Use only tables and columns present in the schema. "
            "Return only the corrected SQL query."
        )