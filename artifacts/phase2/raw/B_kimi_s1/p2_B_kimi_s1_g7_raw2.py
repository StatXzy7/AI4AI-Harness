"""Repair-loop harness: execute each candidate query and feed SQLite errors plus the failed SQL back into regeneration until the query runs or the attempt budget is exhausted."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS1G7(SQLHarness):
    """Error-feedback repair loop around the frozen weak solver.

    Improvement over a single greedy call: every candidate query is actually
    executed against the database. Whenever SQLite rejects it, the offending
    SQL and the exact error message are appended to a failure history in the
    prompt, and the model is asked to diagnose and regenerate. The sampling
    temperature rises slightly on each retry so a deterministic-leaning
    solver does not repeat the identical broken query, and the full failure
    history prevents cycling back to earlier mistakes.
    """

    MAX_ATTEMPTS = 5

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite engineer. Given a database schema and a "
            "natural-language question, you output exactly one valid SQLite "
            "query and nothing else."
        )
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite query that answers the question. "
            "Return only the SQL statement: no explanation, no markdown fences."
        )

        failures = []  # list of (sql_or_output, error_message) already tried
        last_sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            prompt = base_prompt
            if failures:
                history = "\n\n".join(
                    f"Failed attempt {i}:\n{bad}\nSQLite error: {err}"
                    for i, (bad, err) in enumerate(failures, start=1)
                )
                prompt += (
                    "\n\nThe following previous attempts FAILED to execute:\n\n"
                    f"{history}\n\n"
                    "Diagnose why they failed: check table and column names "
                    "against the schema above, quoting of string literals, "
                    "join keys, and function usage. Then return ONE corrected "
                    "SQL statement that differs from all failed attempts. "
                    "Return only the corrected SQL."
                )

            # Greedy first try; raise temperature on repairs so retries are
            # not deterministic replays of the same broken query.
            temperature = 0.0 if attempt == 0 else min(0.2 * attempt, 0.8)
            raw = self.llm(prompt, system=system, temperature=temperature, n=1)
            sql = bridge.extract_sql(raw).strip()

            if not sql:
                failures.append(
                    (raw.strip()[:200] or "<empty model output>",
                     "No SQL statement could be extracted from the reply.")
                )
                continue

            last_sql = sql
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            error = str(result.get("error") or "unknown execution error").strip()
            failures.append((sql, error))

        # Budget exhausted: fall back to the most recent (most-informed) query.
        return last_sql