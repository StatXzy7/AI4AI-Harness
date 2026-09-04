"""Samples 3 SQL candidates from the frozen solver at temperature 0.7, executes each one that parses, and returns the candidate whose result set wins a majority vote."""

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS1Vote3(SQLHarness):
    """Majority-vote harness: 3 independent solver samples, execute all that
    parse, and return the SQL producing the majority result set."""

    NUM_SAMPLES = 3
    SAMPLE_TEMPERATURE = 0.7

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL solver. Given a database schema and "
            "a natural-language question, produce one correct SQL query. "
            "Return only the SQL query."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question."
        )

        # Ask the frozen solver for 3 independent attempts in one call.
        completions = self.llm(
            prompt,
            system=system,
            temperature=self.SAMPLE_TEMPERATURE,
            n=self.NUM_SAMPLES,
        )
        if isinstance(completions, str):
            completions = [completions]
        completions = [c for c in (completions or []) if c]

        # Extract SQL from every completion; keep only candidates that parse.
        parsed = []
        for text in completions:
            try:
                sql = (bridge.extract_sql(text) or "").strip()
            except Exception:
                sql = ""
            if sql:
                parsed.append(sql)

        if not parsed:
            # Nothing parseable: return the raw first completion as a last resort.
            return completions[0].strip() if completions else ""

        # Execute all candidates that parsed; only successful runs get a vote.
        executed = []  # list of (sql, result_key), in candidate order
        for sql in parsed:
            try:
                outcome = self.execute(sql)
            except Exception:
                continue
            if outcome and outcome.get("ok"):
                executed.append((sql, self._rows_key(outcome.get("rows"))))

        if not executed:
            # Every candidate failed to execute: fall back to the first parsed SQL.
            return parsed[0]

        # Majority vote over result sets; ties broken by earliest candidate.
        first_seen = {}
        counts = Counter()
        for sql, key in executed:
            if key not in first_seen:
                first_seen[key] = sql
            counts[key] += 1

        best_key = None
        best_count = -1
        for sql, key in executed:
            if counts[key] > best_count:
                best_key = key
                best_count = counts[key]

        return first_seen[best_key]

    @staticmethod
    def _rows_key(rows):
        """Canonical, hashable, order-insensitive representation of a result set."""
        try:
            normalized = []
            for row in rows or []:
                if isinstance(row, dict):
                    normalized.append(repr(sorted(row.items(), key=lambda kv: str(kv[0]))))
                elif isinstance(row, (list, tuple)):
                    normalized.append(repr(tuple(row)))
                else:
                    normalized.append(repr(row))
            return tuple(sorted(normalized))
        except Exception:
            return repr(rows)