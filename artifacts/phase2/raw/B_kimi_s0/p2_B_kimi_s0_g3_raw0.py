"""Self-consistency voting: sample several SQL candidates, execute each, and return the query whose result set wins the majority vote."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS0G3(SQLHarness):
    """Improves on a single greedy call with execution-guided self-consistency.

    Control flow:
      1. Generate one greedy candidate (temperature 0) plus several
         higher-temperature samples.
      2. Extract SQL from every generation with bridge.extract_sql.
      3. Execute every distinct candidate against the database.
      4. Group successful candidates by their (order-insensitive)
         result-set signature and take a majority vote over signatures,
         counting duplicate generations; ties break toward the greedy
         candidate.
      5. If no candidate executes successfully, fall back to the greedy
         extraction (no error-feedback loop -- selection only).
    """

    NUM_SAMPLES = 4
    SAMPLE_TEMPERATURE = 0.8

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        system = ("You are an expert Text-to-SQL engine. "
                  "Answer with exactly one SQL query and nothing else.")

        candidates = []

        greedy_sql = ""
        try:
            out = self.llm(prompt, system=system, temperature=0.0)
            greedy_sql = bridge.extract_sql(self._as_text(out)) or ""
        except Exception:
            greedy_sql = ""
        if greedy_sql:
            candidates.append(greedy_sql)

        for _ in range(self.NUM_SAMPLES):
            try:
                out = self.llm(prompt, system=system,
                               temperature=self.SAMPLE_TEMPERATURE)
                sql = bridge.extract_sql(self._as_text(out)) or ""
            except Exception:
                sql = ""
            if sql:
                candidates.append(sql)

        if not candidates:
            return greedy_sql

        # Execute each distinct candidate once.
        executions = {}
        for sql in dict.fromkeys(candidates):
            try:
                executions[sql] = self.execute(sql)
            except Exception as exc:
                executions[sql] = {"ok": False, "rows": [], "error": str(exc)}

        # Majority vote over result-set signatures (duplicates count as votes).
        groups = {}
        order = []
        for sql in candidates:
            res = executions.get(sql) or {}
            if not res.get("ok"):
                continue
            sig = self._signature(res.get("rows"))
            if sig not in groups:
                groups[sig] = []
                order.append(sig)
            groups[sig].append(sql)

        if not groups:
            return greedy_sql or candidates[0]

        greedy_sig = None
        if greedy_sql and (executions.get(greedy_sql) or {}).get("ok"):
            greedy_sig = self._signature(executions[greedy_sql].get("rows"))

        best_sig = None
        best_key = None
        for sig in order:
            key = (len(groups[sig]), sig == greedy_sig)
            if best_key is None or key > best_key:
                best_key = key
                best_sig = sig

        if greedy_sig is not None and greedy_sig == best_sig:
            return greedy_sql
        return groups[best_sig][0]

    def _build_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            "Write one SQLite query that answers the question. "
            "Return only the SQL, no markdown, no explanation.\n\n"
            f"Question: {question}\n"
            "SQL:"
        )

    @staticmethod
    def _signature(rows) -> str:
        try:
            return repr(sorted(repr(r) for r in rows))
        except Exception:
            return repr(rows)

    @classmethod
    def _as_text(cls, out) -> str:
        if isinstance(out, str):
            return out
        if isinstance(out, (list, tuple)) and out:
            return cls._as_text(out[0])
        if isinstance(out, dict):
            for key in ("text", "content", "response", "answer"):
                if key in out:
                    return cls._as_text(out[key])
        return "" if out is None else str(out)