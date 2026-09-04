"""Self-consistency harness: sample several SQL candidates, execute each distinct one, and return the candidate whose result-set signature wins the majority vote."""
# MECHANISM: vote        -- you draw multiple samples and select among them

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G6(SQLHarness):
    """Execution-guided self-consistency (majority voting) Text-to-SQL harness.

    Instead of trusting a single greedy generation, this harness:
      1. draws one greedy candidate plus several temperature-sampled candidates,
      2. executes every distinct candidate against the database,
      3. groups the successful executions by a canonical result-set signature,
      4. returns the candidate whose signature collected the most votes
         (identical queries contribute their sampling multiplicity as weight).

    If no candidate executes successfully, the greedy candidate is returned
    unchanged so behavior never degrades below the single-call baseline.
    """

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL system. Given a database schema and a "
        "natural-language question, write one correct SQL query that answers "
        "the question. Output only the SQL query, with no explanation."
    )

    NUM_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.7

    # ------------------------------------------------------------------ API
    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)

        candidates = []

        greedy = self._extract(self._generate(prompt, temperature=0.0))
        if greedy:
            candidates.append(greedy)

        for _ in range(self.NUM_SAMPLES):
            sql = self._extract(self._generate(prompt, temperature=self.SAMPLE_TEMPERATURE))
            if sql:
                candidates.append(sql)

        if not candidates:
            return "SELECT 1"

        # Merge identical queries (preserving order) but remember how often
        # each was sampled; multiplicity becomes vote weight.
        unique_sqls = []
        multiplicity = {}
        for sql in candidates:
            key = self._normalize_sql(sql)
            if key not in multiplicity:
                multiplicity[key] = 0
                unique_sqls.append(sql)
            multiplicity[key] += 1

        # signature -> [votes, first_index, representative_sql, has_rows]
        signatures = {}
        for idx, sql in enumerate(unique_sqls):
            try:
                result = self.execute(sql)
            except Exception:
                continue
            if not result or not result.get("ok"):
                continue
            rows = result.get("rows") or []
            sig = self._signature(rows)
            if sig not in signatures:
                signatures[sig] = [0, idx, sql, bool(rows)]
            signatures[sig][0] += multiplicity[self._normalize_sql(sql)]

        if not signatures:
            # Nothing executed: fall back to the greedy candidate.
            return candidates[0]

        def rank(item):
            votes, first_idx, _sql, has_rows = item[1]
            # Most votes wins; ties prefer a non-empty result, then the
            # earliest (greedy-first) candidate.
            return (votes, 1 if has_rows else 0, -first_idx)

        winning = max(signatures.items(), key=rank)
        return winning[1][2]

    # -------------------------------------------------------------- helpers
    def _build_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL query that answers the question. "
            "Return only the SQL."
        )

    def _generate(self, prompt: str, temperature: float) -> str:
        try:
            text = self.llm(
                prompt,
                system=self.SYSTEM_PROMPT,
                temperature=temperature,
                n=1,
            )
        except Exception:
            return ""
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        return text if isinstance(text, str) else str(text)

    def _extract(self, text: str) -> str:
        if not text:
            return ""
        try:
            sql = bridge.extract_sql(text) or ""
        except Exception:
            sql = ""
        sql = sql.strip()
        return sql if sql else text.strip()

    @staticmethod
    def _normalize_sql(sql: str) -> str:
        return " ".join(sql.split()).lower()

    @staticmethod
    def _canon(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, float):
            return round(value, 6)
        if isinstance(value, str):
            return " ".join(value.split())
        if value is None or isinstance(value, int):
            return value
        return str(value)

    def _signature(self, rows) -> str:
        """Canonical, order-insensitive fingerprint of a result set."""
        try:
            norm_rows = []
            for row in rows:
                if isinstance(row, dict):
                    norm = tuple(
                        sorted((str(k), self._canon(v)) for k, v in row.items())
                    )
                elif isinstance(row, (list, tuple)):
                    norm = tuple(self._canon(v) for v in row)
                else:
                    norm = self._canon(row)
                norm_rows.append(repr(norm))
            norm_rows.sort()
            return "\n".join(norm_rows)
        except Exception:
            return repr(rows)