"""Execute each candidate SQL against the real database and feed the exact execution error back to the frozen solver for up to three corrective regeneration rounds, escalating sampling temperature whenever a repair stalls."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G0(SQLHarness):
    """Error-feedback repair harness around the frozen weak solver.

    Control flow (a real change vs. a single greedy call):

      1. Initial greedy generation of one SQL statement from schema + question.
      2. Candidate hygiene: markdown fences, leading comments, and trailing
         semicolons are stripped; the statement is rejected unless it is
         read-only (SELECT / WITH ... SELECT), so the database is never
         mutated by a misbehaving generation.
      3. The candidate is executed on the actual database via self.execute.
      4. On failure (or policy violation) the exact SQLite error and the
         offending SQL are folded into a repair prompt and the solver
         regenerates; this repeats for at most MAX_REPAIR_ROUNDS rounds.
      5. If a repair round returns the identical broken SQL (a stall), the
         sampling temperature is escalated (0.3 -> 0.6 -> 0.9) to escape the
         failure mode; otherwise generation stays greedy and deterministic.
      6. The first query that executes cleanly is returned; if every round
         fails, the last non-empty candidate is returned as a best effort.
    """

    MAX_REPAIR_ROUNDS = 3
    READ_ONLY_PREFIXES = ("select", "with")
    MAX_TEMPERATURE = 0.9
    TEMPERATURE_STEP = 0.3

    SYSTEM_PROMPT = (
        "You are a meticulous SQLite expert. Translate the question into exactly one "
        "valid, read-only SQLite SELECT statement that uses only tables and columns "
        "present in the given schema. Output only the SQL statement."
    )

    # ------------------------------------------------------------------ solve

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        schema = getattr(self, "schema", "") or ""

        failures = []      # [(sql, error_message)] for every rejected attempt
        prev_sql = ""
        stall_count = 0
        last_sql = ""

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            if failures:
                prompt = self._repair_prompt(schema, question, failures)
            else:
                prompt = self._initial_prompt(schema, question)

            # Greedy by default; escalate only after a repair round reproduced
            # the exact same (broken) statement.
            temperature = 0.0
            if round_idx > 0 and stall_count > 0:
                temperature = min(self.MAX_TEMPERATURE,
                                  self.TEMPERATURE_STEP * stall_count)

            response = self._generate(prompt, temperature)
            sql = self._normalize(bridge.extract_sql(response))

            # Stall detection: the repair returned the identical statement.
            stall_count = stall_count + 1 if (sql and sql == prev_sql) else 0
            prev_sql = sql
            if sql:
                last_sql = sql

            if not sql:
                failures.append(
                    ("", "No SQL statement could be extracted from the reply.")
                )
                continue

            # Policy gate runs BEFORE execution, so destructive SQL is never run.
            error = self._policy_error(sql)
            if error is None:
                ok, exec_error = self._try_execute(sql)
                if ok:
                    return sql  # clean execution: ship it
                error = exec_error or "Execution failed for an unknown reason."

            failures.append((sql, error))

        # Every round failed: return the most recent (best-informed) candidate.
        return last_sql or "SELECT 1"

    # ------------------------------------------------------------- prompting

    def _initial_prompt(self, schema: str, question: str) -> str:
        return (
            "Database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite SELECT statement that answers the question. "
            "Reply with only the SQL statement."
        )

    def _repair_prompt(self, schema: str, question: str, failures) -> str:
        lines = [
            "Database schema:",
            schema,
            "",
            f"Question: {question}",
            "",
            "Your previous SQL attempts failed against this database:",
        ]
        for i, (sql, error) in enumerate(failures, 1):
            err = " ".join(str(error).split()) or "unknown error"
            lines.append(f"{i}. SQL: {sql if sql else '(empty)'}")
            lines.append(f"   SQLite error: {err[:400]}")
        lines.append("")
        lines.append(
            "Write a corrected, read-only SQLite SELECT statement that avoids every "
            "error above. Re-check table and column names against the schema, quoting, "
            "JOIN conditions, and aggregation. Reply with only the SQL statement."
        )
        return "\n".join(lines)

    def _generate(self, prompt: str, temperature: float) -> str:
        try:
            out = self.llm(prompt, system=self.SYSTEM_PROMPT,
                           temperature=temperature, n=1)
        except TypeError:
            # Defensive fallback for a stricter frozen-solver signature.
            out = self.llm(prompt)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if out is None:
            return ""
        return out if isinstance(out, str) else str(out)

    # ------------------------------------------------------------ SQL checks

    def _normalize(self, sql: str) -> str:
        sql = (sql or "").strip()
        if sql.startswith("