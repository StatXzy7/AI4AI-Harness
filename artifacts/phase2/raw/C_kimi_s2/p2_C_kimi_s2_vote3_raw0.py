"""Sample 3 independent SQL candidates from the frozen solver at temperature 0.7, execute every candidate that parses, and return the candidate whose execution result wins the majority vote."""

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2Vote3(SQLHarness):
    """Self-consistency harness: n=3 samples at T=0.7, execution-result majority vote."""

    N_SAMPLES = 3
    TEMPERATURE = 0.7

    def solve(self, question: str) -> str:
        system = (
            "You are a precise Text-to-SQL engine. Given a database schema and a "
            "natural-language question, you output exactly one SQL query and nothing else."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that correctly answers the question. "
            "Output only the SQL query, with no explanation."
        )

        # Step 1: ask the frozen solver for 3 independent attempts in one call.
        raw = self.llm(prompt, system=system, temperature=self.TEMPERATURE, n=self.N_SAMPLES)
        completions = self._as_list(raw)

        # Step 2: parse each attempt and execute every candidate that parses.
        first_parsed_sql = ""
        executed = []  # (sql, result_key) for candidates that parsed and ran successfully
        for text in completions:
            sql = bridge.extract_sql(text if isinstance(text, str) else str(text))
            if not sql:
                continue  # attempt did not parse -> skipped
            if not first_parsed_sql:
                first_parsed_sql = sql
            outcome = self.execute(sql)
            if outcome.get("ok"):
                executed.append((sql, self._result_key(outcome.get("rows"))))

        # Step 3: majority vote over execution results (ties -> earliest executed).
        if executed:
            counts = Counter(key for _sql, key in executed)
            winning_key = counts.most_common(1)[0][0]
            for sql, key in executed:
                if key == winning_key:
                    return sql

        # Fallbacks (rare): no candidate executed successfully.
        if first_parsed_sql:
            return first_parsed_sql
        for text in completions:
            text = (text if isinstance(text, str) else str(text)).strip()
            if text:
                return text
        return "SELECT 1"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _as_list(raw):
        """Normalize self.llm(..., n=3) output to a list of completion strings."""
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, (list, tuple)):
            return list(raw)
        return [str(raw)]

    @staticmethod
    def _result_key(rows):
        """Order-insensitive, hashable canonical form of an execution result."""
        def row_key(r):
            if isinstance(r, dict):
                return tuple(sorted((str(k), repr(v)) for k, v in r.items()))
            if isinstance(r, (list, tuple)):
                return tuple(repr(v) for v in r)
            return (repr(r),)

        try:
            return tuple(sorted(row_key(r) for r in (rows or [])))
        except Exception:
            return repr(rows)