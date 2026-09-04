"""Execution-guided self-consistency: sample several SQL candidates, run each, and return the candidate whose execution result wins the majority vote."""

# MECHANISM: vote        -- you draw multiple samples and select among them

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS1G4(SQLHarness):
    """Text-to-SQL harness using execution-based self-consistency voting.

    Improvement over a single greedy generation:
      1. Draw one greedy sample plus several temperature>0 samples.
      2. Extract and deduplicate the SQL candidates.
      3. Execute every candidate against the database.
      4. Group the successful executions by their (order-insensitive) result
         sets and return the candidate belonging to the largest group
         (majority vote over actual query answers, not over SQL text).
      5. Fall back to the greedy candidate if nothing executes successfully.
    """

    NUM_SAMPLES = 5            # 1 greedy + (NUM_SAMPLES - 1) diverse samples
    SAMPLE_TEMPERATURE = 0.7   # diversity for the non-greedy samples

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        system = (
            "You are an expert data analyst. Given a database schema and a "
            "natural language question, you write one correct, executable SQL "
            "query. You answer with the SQL query only."
        )

        # 1) Draw candidates: one greedy, the rest sampled for diversity.
        raw_outputs = [self._generate(prompt, system, temperature=0.0)]
        for _ in range(self.NUM_SAMPLES - 1):
            raw_outputs.append(
                self._generate(prompt, system, temperature=self.SAMPLE_TEMPERATURE)
            )

        # 2) Extract SQL and deduplicate while preserving generation order
        #    (index 0 is always the greedy candidate).
        candidates = []
        seen = set()
        for raw in raw_outputs:
            sql = ""
            if raw:
                try:
                    sql = (bridge.extract_sql(raw) or "").strip()
                except Exception:
                    sql = raw.strip()
            if sql and sql not in seen:
                seen.add(sql)
                candidates.append(sql)

        if not candidates:
            return (raw_outputs[0] or "").strip()

        # 3) Execute each unique candidate.
        executed = []
        for sql in candidates:
            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive: treat harness errors as failure
                result = {"ok": False, "rows": [], "error": str(exc)}
            if not isinstance(result, dict):
                result = {"ok": False, "rows": [], "error": "bad result"}
            executed.append((sql, result))

        # 4) Vote: group successful executions by normalized result set.
        groups = {}
        for idx, (_sql, result) in enumerate(executed):
            if result.get("ok"):
                key = self._result_key(result.get("rows"))
                groups.setdefault(key, []).append(idx)

        if not groups:
            # Nothing executed: fall back to the greedy candidate.
            return candidates[0]

        # Largest group wins; ties break toward the earliest-generated
        # candidate (favouring the greedy sample).
        best_key = max(groups.keys(), key=lambda k: (len(groups[k]), -min(groups[k])))
        winner_idx = min(groups[best_key])
        return executed[winner_idx][0]

    # -------------------------------------------------------------- helpers

    def _build_prompt(self, question: str) -> str:
        return (
            "Here is the database schema:\n\n"
            f"{self.schema}\n\n"
            "Write a single SQL query that answers the following question. "
            "Return only the SQL query, with no explanation or commentary.\n\n"
            f"Question: {question}"
        )

    def _generate(self, prompt: str, system: str, temperature: float) -> str:
        """Call the frozen LLM and normalize its return value to a string."""
        try:
            out = self.llm(prompt, system=system, temperature=temperature, n=1)
        except TypeError:
            # In case the frozen solver does not accept keyword arguments.
            out = self.llm(prompt, system, temperature, 1)
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            return str(out[0]) if out else ""
        return "" if out is None else str(out)

    def _result_key(self, rows):
        """Canonical, hashable representation of a result set.

        Row order is ignored (bag semantics) so that equivalent queries whose
        results only differ in ordering still vote together.
        """
        if rows is None:
            return ("__null_rows__",)
        normalized = []
        try:
            iterator = list(rows)
        except TypeError:
            return (repr(rows),)
        for row in iterator:
            if isinstance(row, dict):
                normalized.append(
                    tuple(sorted((str(k), self._value_key(v)) for k, v in row.items()))
                )
            elif isinstance(row, (list, tuple)):
                normalized.append(tuple(self._value_key(v) for v in row))
            else:
                normalized.append((self._value_key(row),))
        return tuple(sorted(normalized))

    @staticmethod
    def _value_key(value):
        if isinstance(value, float):
            # Avoid splitting votes over insignificant float noise.
            return ("num", round(value, 6))
        if isinstance(value, (int, str, bool)) or value is None:
            return (type(value).__name__, value)
        return (type(value).__name__, repr(value))