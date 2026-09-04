"""Execute-and-repair loop: each greedy SQL candidate is executed against the live database and any execution error is fed back to the frozen solver to drive a corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G1(SQLHarness):
    """Frozen-solver wrapper that adds an execute-and-repair control loop.

    Control flow (a real change versus a single greedy call):

    1. Generate SQL greedily from (schema, question).
    2. Execute the extracted candidate on the real database.
    3. If execution fails, re-prompt the frozen solver with the failed SQL
       and the database error message so it can produce a corrected query.
    4. Repeat steps 2-3 for up to ``max_attempts`` generations in total.
    5. Return the first candidate that executes cleanly; if none does,
       return the most recent non-empty candidate as a best effort.
    """

    # Total generations per question: 1 initial + (max_attempts - 1) repairs.
    max_attempts = 3

    GEN_SYSTEM = (
        "You are an expert text-to-SQL engine. Using only the tables and "
        "columns shown in the schema, write a single SQLite query that "
        "answers the question. Output the SQL statement only."
    )

    FIX_SYSTEM = (
        "You are an expert text-to-SQL engine repairing broken queries. "
        "Read the database error messages carefully, then output a single "
        "corrected SQLite query that answers the question. Output the SQL "
        "statement only."
    )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _call_llm(self, prompt: str, system: str) -> str:
        """One call to the frozen solver, with output normalised to ``str``."""
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):  # some backends return sample lists
            out = out[0] if out else ""
        if not isinstance(out, str):
            out = str(out)
        return out

    def _run_sql(self, sql: str) -> dict:
        """Execute ``sql`` defensively so executor faults become failures."""
        try:
            res = self.execute(sql)
        except Exception as exc:  # backend safety net: never kill the loop
            return {"ok": False, "rows": [], "error": "executor raised: %r" % (exc,)}
        if not isinstance(res, dict):
            return {"ok": False, "rows": [], "error": "executor returned a non-dict result"}
        return res

    @staticmethod
    def _reason(res: dict) -> str:
        msg = str(res.get("error") or "").strip()
        return msg if msg else "query execution failed"

    # ------------------------------------------------------------------ #
    # Entry point                                                        #
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        failures = []    # [(sql, reason)] for every failed generation
        candidate = ""   # most recent non-empty SQL, kept as last resort

        for attempt in range(1, self.max_attempts + 1):

            # -- 1. build prompt: fresh on attempt 1, repair afterwards --- #
            if attempt == 1:
                prompt = (
                    f"Database schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    "Write one SQLite query that answers the question."
                )
                system = self.GEN_SYSTEM
            else:
                history = "\n\n".join(
                    "Attempt {}\nSQL:\n{}\nError:\n{}".format(
                        i,
                        sql if sql else "(no SQL could be extracted from the model output)",
                        reason,
                    )
                    for i, (sql, reason) in enumerate(failures, start=1)
                )
                prompt = (
                    f"Database schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    "Every query generated so far failed to run:\n\n"
                    f"{history}\n\n"
                    "Write one corrected SQLite query that answers the "
                    "question and avoids these errors."
                )
                system = self.FIX_SYSTEM

            # -- 2. generate and extract ---------------------------------- #
            text = self._call_llm(prompt, system)
            sql = (bridge.extract_sql(text) or "").strip()

            if not sql:
                failures.append(("", "the model output contained no SQL statement"))
                continue

            candidate = sql

            # -- 3. execute; success escapes the loop immediately --------- #
            res = self._run_sql(sql)
            if res.get("ok"):
                return sql

            failures.append((sql, self._reason(res)))

        # All attempts failed: best effort is the latest non-empty candidate.
        return candidate