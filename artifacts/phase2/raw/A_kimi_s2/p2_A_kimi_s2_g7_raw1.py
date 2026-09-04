"""Repair loop: generate SQL greedily, execute each candidate, and feed database errors (or suspicious empty results) back as feedback until a valid query is found or the attempt budget is exhausted."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G7(SQLHarness):
    """Text-to-SQL harness with an execution-feedback repair loop.

    Instead of trusting a single greedy generation, each candidate query is
    executed against the database. Failures (syntax errors, bad column names,
    etc.) are appended to the prompt so the frozen solver can regenerate a
    corrected query. A query that runs but returns zero rows is kept as a
    fallback while the solver is asked to double-check it, since empty results
    often indicate a wrong filter value or join.
    """

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert text-to-SQL assistant. Given a database schema "
            "and a natural-language question, output ONLY the SQL query that "
            "answers the question. No markdown fences, no commentary, no "
            "explanation -- just the raw SQL."
        )
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. "
            "Output only the SQL."
        )

        prompt = base_prompt
        fallback_sql = ""  # first executable SQL, possibly with zero rows
        last_sql = ""

        for _ in range(self.MAX_ATTEMPTS):
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
            sql = bridge.extract_sql(response)

            if not sql:
                # Nothing parseable: ask again with a stricter instruction.
                prompt = (
                    base_prompt
                    + "\n\nYour previous reply contained no parseable SQL. "
                    "Respond with ONLY the SQL query and nothing else."
                )
                continue

            if sql == fallback_sql:
                # Solver insists the zero-row query is correct; accept it.
                return fallback_sql

            last_sql = sql
            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive: treat crashes as errors
                result = {"ok": False, "rows": [], "error": str(exc)}

            if result.get("ok"):
                rows = result.get("rows") or []
                if rows:
                    return sql
                # Executable but empty result: keep as fallback, ask the
                # solver to re-examine filters/joins once.
                if not fallback_sql:
                    fallback_sql = sql
                prompt = (
                    base_prompt
                    + "\n\nThis SQL executed successfully but returned ZERO "
                    "rows:\n"
                    f"{sql}\n\n"
                    "Re-check string filter values, column choices, and joins "
                    "against the schema and question. If the query is truly "
                    "correct, repeat it exactly; otherwise output a corrected "
                    "query. Output only SQL."
                )
            else:
                error = result.get("error", "unknown database error")
                prompt = (
                    base_prompt
                    + "\n\nYour previous SQL FAILED to execute.\n"
                    f"Failing SQL:\n{sql}\n\n"
                    f"Database error:\n{error}\n\n"
                    "Fix the query so it runs on this schema. "
                    "Output only the corrected SQL."
                )

        # Budget exhausted: prefer a query that at least executed cleanly.
        return fallback_sql or last_sql