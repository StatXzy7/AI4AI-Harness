"""Sample three independent SQL candidates from the frozen solver (n=3, temperature=0.7), execute every one that parses, and return the query whose result wins the majority vote."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS1Vote3(SQLHarness):
    """Self-consistency wrapper: 3 sampled SQLs, execute all that parse, return the majority result."""

    N_ATTEMPTS = 3
    TEMPERATURE = 0.7

    SYSTEM = (
        "You are an expert SQLite programmer. "
        "Reply with exactly one SQL query and nothing else."
    )

    def solve(self, question: str) -> str:
        # --- 1) Ask the frozen solver for 3 independent SQL attempts. ---
        prompt = self._build_prompt(question)
        raw = self.llm(
            prompt,
            system=self.SYSTEM,
            temperature=self.TEMPERATURE,
            n=self.N_ATTEMPTS,
        )
        candidates = self._as_texts(raw)

        # --- 2) Parse every attempt; keep original order, drop non-parsing ones. ---
        parsed = []
        for text in candidates:
            sql = self._extract(text)
            if sql:
                parsed.append(sql)

        # --- 3) Execute ALL attempts that parsed (duplicates included). ---
        outcomes = [(sql, self._run(sql)) for sql in parsed]

        # --- 4) Majority vote over execution results (canonicalized rows). ---
        counts = {}        # result key -> number of attempts producing it
        winner_sql = {}    # result key -> first (lowest-index) SQL producing it
        for sql, outcome in outcomes:
            if outcome is None or not outcome.get("ok"):
                continue  # failed executions do not earn a result vote
            key = self._canonical(outcome.get("rows"))
            counts[key] = counts.get(key, 0) + 1
            if key not in winner_sql:
                winner_sql[key] = sql

        # Deterministic argmax: strict '>' keeps the earliest result on ties.
        best_key = None
        best_count = 0
        for key, count in counts.items():
            if count > best_count:
                best_key, best_count = key, count

        if best_key is not None:
            return winner_sql[best_key]

        # --- Fallbacks (no attempt executed successfully). ---
        if parsed:                       # nothing executed, but something parsed
            return parsed[0]
        if candidates:                   # nothing even parsed
            return candidates[0].strip()
        return ""

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _build_prompt(self, question: str) -> str:
        schema = getattr(self, "schema", None) or ""
        return (
            "Database schema (SQLite):\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write one valid SQLite SQL query that answers the question. "
            "Output only the SQL query."
        )

    @staticmethod
    def _as_texts(raw):
        """Normalize the llm() return value into a list of plain strings."""
        if raw is None:
            return []
        if isinstance(raw, (list, tuple)):
            items = raw
        else:
            items = [raw]
        texts = []
        for item in items:
            if isinstance(item, str):
                texts.append(item)
            else:
                text = getattr(item, "text", None)
                texts.append(text if isinstance(text, str) else str(item))
        return texts

    @staticmethod
    def _extract(text):
        """Extract SQL from one completion; '' if it does not parse."""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            return ""
        if not isinstance(sql, str):
            return ""
        return sql.strip()

    def _run(self, sql):
        """Execute a query defensively; None if the executor itself blows up."""
        try:
            return self.execute(sql)
        except Exception:
            return None

    @staticmethod
    def _canonical(rows):
        """Hashable, comparable key for an execution result."""
        try:
            return repr(rows)
        except Exception:
            return str(rows)