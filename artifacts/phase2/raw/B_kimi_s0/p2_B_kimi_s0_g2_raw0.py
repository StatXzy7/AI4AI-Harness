"""Execute-and-repair harness: generate SQL, run it, and feed execution errors back to the LLM for iterative regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS0G2(SQLHarness):
    """Repair loop: initial greedy generation, then up to N error-driven fixes.

    Each failed execution's error message is appended to a running feedback
    block so the model sees the full history of broken attempts.  Retries use
    a small nonzero temperature so a deterministic re-decode does not simply
    reproduce the same broken query.
    """

    MAX_ATTEMPTS = 4
    MAX_ERROR_CHARS = 500

    def solve(self, question: str) -> str:
        system = (
            "You are an expert text-to-SQL assistant. Given a database schema "
            "and a natural-language question, produce exactly one correct SQL "
            "query. Output only the SQL query: no explanation, no markdown "
            "fences, no comments."
        )
        schema_block = f"Database schema:\n{self.schema}\n\nQuestion: {question}\n"

        prompt = (
            schema_block
            + "\nWrite a single SQL query that answers the question."
        )

        failures = []  # list of (sql, error) that did not execute
        last_sql = "SELECT 1"

        for attempt in range(self.MAX_ATTEMPTS):
            # Deterministic first pass; slight diversity on repair passes so
            # the model can escape the failure mode it just produced.
            temperature = 0.0 if attempt == 0 else min(0.2 * attempt, 0.6)

            response = self.llm(
                prompt, system=system, temperature=temperature, n=1
            )
            text = (
                response[0]
                if isinstance(response, (list, tuple))
                else response
            )
            sql = bridge.extract_sql(text) or text.strip()
            if not sql:
                sql = last_sql
            last_sql = sql

            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive: treat harness errors as SQL errors
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                return sql

            error = str(result.get("error", "unknown execution error"))
            error = error[: self.MAX_ERROR_CHARS]
            failures.append((sql, error))

            history = "\n\n".join(
                f"Attempt {i + 1} SQL:\n{s}\nExecution error: {e}"
                for i, (s, e) in enumerate(failures)
            )
            prompt = (
                schema_block
                + "\nThe following SQL attempt(s) failed to execute:\n\n"
                + history
                + "\n\nDiagnose why the query failed (check table/column names "
                "against the schema, join keys, and SQL dialect), then output "
                "only the corrected SQL query."
            )

        # All attempts failed: return the most recent candidate so downstream
        # consumers still receive syntactically plausible SQL.
        return last_sql