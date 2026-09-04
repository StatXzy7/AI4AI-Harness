"""Self-consistency voting: sample 3 independent SQL candidates at temperature 0.7, execute every one that parses, and return the SQL whose result set wins the majority vote."""

from collections import OrderedDict

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS1Vote3(SQLHarness):
    """3-way self-consistency voting wrapper around the frozen weak solver."""

    name = "P2P2DGlmS1Vote3"

    # Voting parameters (kept explicit in the control flow, not just the prompt).
    N_CANDIDATES = 3
    TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL translator. Given a database schema and a "
        "question, write exactly one SQLite query that answers the question. "
        "Output only the SQL query, with no explanation."
    )

    USER_TEMPLATE = (
        "Database schema:\n"
        "{schema}\n\n"
        "Question: {question}\n\n"
        "SQL query:"
    )

    def solve(self, question: str) -> str:
        prompt = self.USER_TEMPLATE.format(schema=self.schema, question=question)

        # --- Step 1: 3 independent attempts at temperature 0.7 -----------------
        raw = self.llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=self.TEMPERATURE,
            n=self.N_CANDIDATES,
        )
        if isinstance(raw, str):  # tolerate single-string returns
            raw = [raw]

        # --- Step 2: parse every attempt, keep the ones yielding SQL ----------
        candidates = []
        for text in raw:
            sql = (bridge.extract_sql(text) or "").strip().rstrip(";").strip()
            if sql:
                candidates.append(sql)

        if not candidates:
            return ""

        # --- Step 3: execute ALL candidates that parsed ------------------------
        executed = []  # list of (sql, result_signature) for successful runs
        for sql in candidates:
            try:
                outcome = self.execute(sql)
            except Exception:
                outcome = None
            if outcome and outcome.get("ok"):
                executed.append((sql, self._result_signature(outcome.get("rows"))))

        if not executed:
            # Nothing executed successfully: deterministically fall back to the
            # first parsed candidate rather than voting among failures.
            return candidates[0]

        # --- Step 4: majority vote over normalized result sets ----------------
        counts = OrderedDict()  # signature -> count, insertion order = first seen
        for _sql, sig in executed:
            counts[sig] = counts.get(sig, 0) + 1

        best_sig = None
        best_count = -1
        for sig, count in counts.items():
            if count > best_count:  # strict '>' ties broken by first appearance
                best_count = count
                best_sig = sig

        # --- Step 5: return the SQL behind the majority result ----------------
        for sql, sig in executed:
            if sig == best_sig:
                return sql

        return candidates[0]  # unreachable safeguard

    @staticmethod
    def _result_signature(rows):
        """Canonical, hashable fingerprint of a result set, for vote equality."""
        if rows is None:
            rows = []
        try:
            return tuple(
                tuple("NULL" if v is None else str(v) for v in row)
                for row in rows
            )
        except TypeError:
            # Non-iterable / unexpected row shapes: degrade to a repr fingerprint.
            return repr(rows)