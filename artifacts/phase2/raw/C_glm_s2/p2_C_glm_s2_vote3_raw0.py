"""Harness that asks a frozen text-to-SQL solver for 3 independent SQL attempts (n=3, temperature=0.7), executes every attempt that parses, and returns the SQL whose execution result wins the majority vote."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS2Vote3(SQLHarness):
    """P2P2CGlmS2Vote3 samples three independent SQL candidates at temperature 0.7 and returns the candidate backed by the majority of their execution results."""

    # Number of independent SQL attempts requested from the frozen solver.
    N_SAMPLES = 3
    # Sampling temperature: > 0 so the attempts are genuinely independent.
    TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are a careful text-to-SQL translator. Given a database schema and "
        "a question, reply with exactly one SQL query and nothing else: no "
        "explanation, no markdown fences, no comments."
    )

    def solve(self, question: str) -> str:
        # Step 1: ask the solver for 3 independent SQL attempts -- a single
        # call with n=3 and temperature=0.7 (sampling and voting live in this
        # control flow, not inside the prompt).
        attempts = self._sample_attempts(question or "")

        # Step 2: keep every attempt from which a SQL statement parses.
        parsed = self._parse_attempts(attempts)

        # Step 3: execute *all* of the parsed candidates.
        executed = self._execute_all(parsed)

        # Step 4: majority vote over the execution results.
        winner = self._vote(executed)
        if winner is not None:
            return winner

        # Degenerate fallbacks (no successful execution, or nothing even
        # parsed): best-effort, fully deterministic last resorts.
        if parsed:
            return parsed[0]
        if attempts:
            return attempts[0].strip()
        return ""

    # -- step 1: sample ---------------------------------------------------

    def _sample_attempts(self, question):
        """One call to the frozen solver: n=3 independent samples at 0.7."""
        raw = self.llm(
            self._build_prompt(question),
            system=self.SYSTEM_PROMPT,
            temperature=self.TEMPERATURE,
            n=self.N_SAMPLES,
        )
        if raw is None:
            return []
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, (list, tuple)):
            return [self._coerce_text(item) for item in raw]
        return [self._coerce_text(raw)]

    def _build_prompt(self, question):
        schema = (getattr(self, "schema", None) or "").strip()
        return (
            "Database schema:\n"
            + (schema if schema else "(no schema provided)")
            + "\n\n"
            + "Task: write a single SQL query that answers the question below.\n"
            + "Reply with the SQL query only.\n\n"
            + "Question: "
            + question.strip()
        )

    # -- step 2: parse ----------------------------------------------------

    def _parse_attempts(self, attempts):
        """Extract SQL from each attempt, keeping only those that parse."""
        parsed = []
        for text in attempts:
            if not isinstance(text, str) or not text.strip():
                continue
            try:
                sql = bridge.extract_sql(text)
            except Exception:
                continue
            if isinstance(sql, str) and sql.strip():
                parsed.append(sql.strip())
        return parsed

    # -- step 3: execute --------------------------------------------------

    def _execute_all(self, parsed):
        """Execute every parsed candidate; returns (sql, result) pairs."""
        executed = []
        for sql in parsed:
            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive: executor may raise
                result = {"ok": False, "rows": [], "error": str(exc)}
            if not isinstance(result, dict):
                result = {"ok": False, "rows": [], "error": "malformed result"}
            executed.append((sql, result))
        return executed

    # -- step 4: vote -----------------------------------------------------

    def _vote(self, executed):
        """Return the SQL behind the majority execution result, else None."""
        tallies = {}  # canonical result key -> [votes, first_sql, first_index]
        for index, (sql, result) in enumerate(executed):
            if not result.get("ok"):
                continue  # failed executions cast no vote
            key = self._result_key(result.get("rows"))
            if key not in tallies:
                tallies[key] = [0, sql, index]
            tallies[key][0] += 1
        if not tallies:
            return None
        # Most votes wins; ties break toward the earliest attempt.
        best = max(tallies.values(), key=lambda t: (t[0], -t[2]))
        return best[1]

    @staticmethod
    def _result_key(rows):
        """Hashable, row-order-insensitive canonical form of a result set."""
        row_keys = []
        for row in rows or []:
            if isinstance(row, dict):
                row_keys.append(
                    repr(tuple(sorted((str(col), repr(val)) for col, val in row.items())))
                )
            elif isinstance(row, (list, tuple)):
                row_keys.append(repr(tuple(repr(val) for val in row)))
            else:
                row_keys.append(repr(row))
        return tuple(sorted(row_keys))

    @staticmethod
    def _coerce_text(item):
        """Best-effort coercion of a single LLM sample to plain text."""
        if isinstance(item, str):
            return item
        if item is None:
            return ""
        if isinstance(item, dict):
            for key in ("text", "content", "response"):
                value = item.get(key)
                if isinstance(value, str):
                    return value
            return ""
        return str(item)