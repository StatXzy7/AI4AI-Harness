"""Draw multiple SQL candidates from the LLM (a greedy anchor plus temperature samples) and select the final answer by majority vote over their executed result rows."""

# MECHANISM: vote

from .. import bridge
from ..harness_base import SQLHarness


class P2P2AGlmS2G3(SQLHarness):
    """Execution-guided self-consistency for Text-to-SQL.

    Instead of trusting a single greedy generation, the harness draws one
    deterministic "anchor" candidate plus several temperature samples, runs
    every distinct candidate against the database, clusters the candidates by
    the result rows they actually produce, and returns a representative of the
    cluster backed by the largest number of samples.  Execution failures are
    simply not counted as votes (errors are never fed back to the LLM).
    """

    NAME = "P2P2AGlmS2G3"

    #: number of stochastic samples drawn on top of the greedy anchor
    N_SAMPLES = 5
    #: temperature used for the stochastic vote samples
    SAMPLE_TEMPERATURE = 0.7
    #: cap on how many rows are used when fingerprinting a result set
    FINGERPRINT_ROWS = 100

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "natural-language question, write exactly one SQLite SELECT query that "
        "answers the question. Output only the SQL statement: no explanations, "
        "no markdown fences, no commentary."
    )

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)

        # ---- 1. draw candidates: 1 greedy anchor + N temperature samples ----
        texts = [self._generate(prompt, 0.0)]
        for _ in range(self.N_SAMPLES):
            texts.append(self._generate(prompt, self.SAMPLE_TEMPERATURE))

        # ---- 2. extract SQL; keep only read-only-looking statements ----
        extracted = []  # (raw_sql, normalized_sql) in draw order
        for text in texts:
            sql = self._extract(text)
            if not sql:
                continue
            norm = self._normalize(sql)
            if not norm.lower().startswith(("select", "with")):
                continue  # never execute or emit anything that is not a read
            extracted.append((sql, norm))

        if not extracted:
            # last-ditch deterministic attempt before giving up
            return self._extract(self._generate(prompt, 0.0))

        # ---- 3. unique statements with their sample multiplicities ----
        order = []           # normalized statements, first-appearance order
        weight = {}          # normalized statement -> number of samples backing it
        representative = {}  # normalized statement -> first raw SQL seen
        for sql, norm in extracted:
            if norm not in weight:
                weight[norm] = 0
                representative[norm] = sql
                order.append(norm)
            weight[norm] += 1

        # ---- 4. execute each distinct statement, cluster by result rows ----
        # clusters: result fingerprint -> {"weight", "sql", "pos"}
        clusters = {}
        for pos, norm in enumerate(order):
            sql = representative[norm]
            rows = self._try_execute(sql)
            if rows is None:
                continue  # execution error -> this candidate casts no vote
            fingerprint = self._fingerprint(rows)
            if fingerprint not in clusters:
                clusters[fingerprint] = {"weight": 0, "sql": sql, "pos": pos}
            clusters[fingerprint]["weight"] += weight[norm]

        # ---- 5. majority vote over executed results ----
        if clusters:
            winner = max(
                clusters.values(),
                key=lambda c: (c["weight"], -c["pos"]),
            )
            return winner["sql"]

        # ---- 6. nothing executed: plurality vote over the SQL text itself ----
        best_index = max(
            range(len(order)),
            key=lambda i: (weight[order[i]], -i),
        )
        return representative[order[best_index]]

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _build_prompt(self, question: str) -> str:
        schema = (getattr(self, "schema", "") or "").strip()
        return (
            "Database schema:\n"
            f"{schema}\n\n"
            f"Question: {(question or '').strip()}\n\n"
            "Write one SQLite SELECT query that answers the question. "
            "Reply with the SQL statement only."
        )

    def _generate(self, prompt: str, temperature: float) -> str:
        """One LLM call; tolerant of slight signature variations."""
        try:
            out = self.llm(
                prompt, system=self.SYSTEM_PROMPT,
                temperature=temperature, n=1,
            )
        except TypeError:
            try:
                out = self.llm(
                    prompt, system=self.SYSTEM_PROMPT,
                    temperature=temperature,
                )
            except TypeError:
                out = self.llm(prompt)
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return "" if out is None else str(out)

    @staticmethod
    def _extract(text: str) -> str:
        try:
            sql = bridge.extract_sql(text or "")
        except Exception:
            return ""
        return (sql or "").strip()

    @staticmethod
    def _normalize(sql: str) -> str:
        """Whitespace-collapsed, semicolon-stripped form used for dedup."""
        return " ".join((sql or "").strip().rstrip(";").split())

    def _try_execute(self, sql: str):
        """Run a statement; return its rows, or None if it failed."""
        try:
            outcome = self.execute(sql)
        except Exception:
            return None
        if not isinstance(outcome, dict) or not outcome.get("ok"):
            return None
        rows = outcome.get("rows")
        return [] if rows is None else rows

    def _fingerprint(self, rows) -> tuple:
        """Hashable, order-sensitive fingerprint of a result set."""
        rows = list(rows or [])
        canon = []
        for row in rows[: self.FINGERPRINT_ROWS]:
            if isinstance(row, dict):
                canon.append(
                    ("d",) + tuple(sorted((str(k), str(v)) for k, v in row.items()))
                )
            elif isinstance(row, (list, tuple)):
                canon.append(
                    ("r",) + tuple("__NULL__" if v is None else str(v) for v in row)
                )
            else:
                canon.append(("s", str(row)))
        return (len(rows), tuple(canon))