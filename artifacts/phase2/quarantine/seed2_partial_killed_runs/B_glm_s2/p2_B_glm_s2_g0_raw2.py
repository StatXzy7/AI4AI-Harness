"""Execute-and-repair loop: the harness greedily generates SQL, runs it against the database, and feeds any execution error back to the model for up to two corrective regenerations."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G0(SQLHarness):
    """Text-to-SQL harness that verifies candidate SQL by execution and
    repairs failures using the database's own error messages.

    Control flow per call to :meth:`solve`:

    1. Greedy generation of a candidate query from (schema, question).
    2. The candidate is executed against the real database.
    3. If execution succeeds, the candidate is returned immediately.
    4. If execution fails, the failed query AND the database error string
       are injected into a repair prompt, and the model regenerates.
    5. Steps 2-4 repeat for up to ``MAX_ATTEMPTS`` total attempts; the final
       repair uses a small temperature so the model can escape a greedy
       fixed point (i.e., re-emitting the identical broken query).
    """

    MAX_ATTEMPTS = 3  # one initial generation + up to two error-driven repairs

    SYSTEM_BASE = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "natural-language question, write a single SQLite SELECT query that "
        "answers the question. Output only the query, in a fenced sql code block."
    )

    SYSTEM_REPAIR = (
        "You are an expert text-to-SQL engine. A previously written query "
        "failed when executed against the database. Using the schema and the "
        "reported error, write a single corrected SQLite SELECT query that "
        "still answers the question. Output only the query, in a fenced sql "
        "code block."
    )

    def solve(self, question: str) -> str:
        schema = self.schema or ""

        base_prompt = (
            "Database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL query that answers this question."
        )

        best = ""            # latest non-empty candidate (best-effort answer)
        prev_sql = ""        # latest candidate that was executed and failed
        last_error = "Execution failed."
        tried = set()        # fingerprints of queries known to have failed

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            # ------------------------------------------------------------ #
            # Stage A: generate (initial call, or repair call conditioned  #
            # on the previous execution error).                            #
            # ------------------------------------------------------------ #
            if attempt == 1:
                text = self._call(base_prompt, self.SYSTEM_BASE, 0.0)
            else:
                repair_prompt = (
                    "Database schema:\n"
                    f"{schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Failed query (attempt {attempt - 1}):\n"
                    f"{prev_sql or best}\n\n"
                    f"Database error:\n{last_error}\n\n"
                    "Write a corrected query that fixes this error and still "
                    "answers the question."
                )
                # Attempts 1..MAX-1 are deterministic; bump temperature on the
                # final repair so the model can escape a greedy fixed point.
                temperature = 0.0 if attempt < self.MAX_ATTEMPTS else 0.4
                text = self._call(repair_prompt, self.SYSTEM_REPAIR, temperature)

            candidate = self._sql_from(text)
            if not candidate:
                last_error = (
                    "No SQL statement could be extracted from the model "
                    "output; emit a single query in a