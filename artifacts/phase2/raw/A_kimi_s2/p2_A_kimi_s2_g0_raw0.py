"""Self-consistency voting: sample several candidate SQL queries, execute each one, and return the query whose execution result wins the majority vote."""
# MECHANISM: vote        -- you draw multiple samples and select among them
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G0(SQLHarness):
    """Execution-guided self-consistency voting for Text-to-SQL.

    Rather than trusting a single greedy decode, the harness draws one greedy
    anchor sample plus several higher-temperature samples, executes every
    distinct candidate against the database, and elects the SQL whose result
    set is produced by the most candidates. Candidates that raise execution
    errors abstain; if nothing executes cleanly, the greedy candidate is the
    fallback, so the harness is never worse than the frozen baseline.
    """

    NUM_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.7
    GREEDY_TEMPERATURE = 0.0

    SYSTEM_PROMPT = (
        "You are an expert SQLite text-to-SQL engine. Given a database schema "
        "and a natural-language question, write one correct SQLite query. "
        "Respond with the SQL only -- no prose, no markdown fences."
    )

    # ------------------------------------------------------------------ API
    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)

        # 1) Draw multiple samples: one greedy anchor + diverse samples.
        raw_outputs = [
            self.llm(prompt, system=self.SYSTEM_PROMPT,
                     temperature=self.GREEDY_TEMPERATURE, n=1)
        ]
        for _ in range(max(0, self.NUM_SAMPLES - 1)):
            raw_outputs.append(
                self.llm(prompt, system=self.SYSTEM_PROMPT,
                         temperature=self.SAMPLE_TEMPERATURE, n=1)
            )

        # 2) Extract a candidate SQL string from each sample.
        candidates = []
        for output in raw_outputs:
            sql = self._extract(output)
            if sql:
                candidates.append(sql)

        if not candidates:
            # Nothing parseable: hand back the greedy raw text as a last resort.
            return self._as_text(raw_outputs[0])

        # 3) Execute every distinct candidate once and cache the outcome.
        exec_cache = {}
        for sql in candidates:
            if sql not in exec_cache:
                try:
                    exec_cache[sql] = self.execute(sql)
                except Exception as exc:  # executor should not raise, but stay safe
                    exec_cache[sql] = {"ok": False, "rows": [], "error": str(exc)}

        # 4) Vote: each sample casts one ballot for the result set its SQL
        #    yields; samples whose SQL fails to execute abstain.
        groups = {}  # result signature -> {"count", "sql", "first_idx"}
        for idx, sql in enumerate(candidates):
            outcome = exec_cache.get(sql) or {}
            if not outcome.get("ok"):
                continue
            signature = self._result_signature(outcome.get("rows"))
            group = groups.get(signature)
            if group is None:
                groups[signature] = {"count": 1, "sql": sql, "first_idx": idx}
            else:
                group["count"] += 1
                if idx < group["first_idx"]:
                    group["first_idx"] = idx
                    group["sql"] = sql

        if groups:
            winner = max(groups.values(),
                         key=lambda g: (g["count"], -g["first_idx"]))
            return winner["sql"]

        # 5) Every candidate failed to execute: fall back to the greedy decode.
        return candidates[0]

    # ------------------------------------------------------------- helpers
    def _build_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            "Write a single SQLite query that answers the question below. Use "
            "only tables and columns that appear in the schema.\n\n"
            f"Question: {question}\n"
            "SQL:"
        )

    @staticmethod
    def _as_text(output) -> str:
        if isinstance(output, str):
            return output
        if isinstance(output, (list, tuple)) and output:
            return str(output[0])
        return str(output)

    @classmethod
    def _extract(cls, output) -> str:
        text = cls._as_text(output)
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""
        return (sql or "").strip()

    @staticmethod
    def _result_signature(rows) -> str:
        """Order-insensitive, type-tolerant fingerprint of an execution result."""
        try:
            normalized = []
            for row in rows or []:
                if isinstance(row, dict):
                    normalized.append(tuple(sorted(row.items())))
                elif isinstance(row, (list, tuple)):
                    normalized.append(tuple(row))
                else:
                    normalized.append((row,))
            try:
                normalized = sorted(normalized)
            except TypeError:
                pass
            return repr(normalized)
        except Exception:
            return repr(rows)