"""Self-consistency Text-to-SQL harness: sample 3 independent SQL candidates at temperature 0.7, execute every candidate that parses, and return the SQL whose execution result wins the majority vote."""

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2Vote3(SQLHarness):
    """3-sample self-consistency: majority vote over execution result sets."""

    _SYSTEM = (
        "You are an expert Text-to-SQL engine. Given a database schema and a "
        "natural-language question, produce exactly one correct SQL query. "
        "Output only the SQL."
    )

    def solve(self, question: str) -> str:
        prompt = (
            "Write a single SQL query that answers the question below using "
            "the provided database schema.\n\n"
            f"### Database schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            "### SQL\n"
        )

        # --- Step 1: ask the solver for 3 independent attempts (n=3, T=0.7) ---
        raw = self.llm(prompt, system=self._SYSTEM, temperature=0.7, n=3)
        if isinstance(raw, str):
            completions = [raw]
        else:
            completions = [c for c in raw if isinstance(c, str)]

        # --- Step 2: keep only the attempts that parse into SQL ----------------
        candidates = []
        for text in completions:
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                candidates.append(sql.strip())

        if not candidates:
            # Nothing parsed: deterministic retry so we still return something.
            retry = self.llm(prompt, system=self._SYSTEM, temperature=0.0, n=1)
            if isinstance(retry, (list, tuple)):
                retry = retry[0] if retry else ""
            sql = bridge.extract_sql(retry)
            return sql.strip() if sql and sql.strip() else str(retry)

        # --- Step 3: execute every parseable candidate -------------------------
        executed = []  # list of (sql, canonical_result) for successful runs
        for sql in candidates:
            try:
                outcome = self.execute(sql)
            except Exception:
                continue
            if isinstance(outcome, dict) and outcome.get("ok"):
                executed.append((sql, self._canon(outcome.get("rows"))))

        if not executed:
            # No candidate executed successfully; fall back to the first parse.
            return candidates[0]

        # --- Step 4: majority vote over execution results ----------------------
        counts = Counter(key for _, key in executed)
        best_sql, best_count = None, -1
        for sql, key in executed:
            if counts[key] > best_count:  # ties keep the earliest candidate
                best_sql, best_count = sql, counts[key]
        return best_sql

    @staticmethod
    def _canon(rows):
        """Hashable canonical form of a result set (row-order insensitive)."""
        try:
            canon_rows = []
            for row in rows or []:
                if isinstance(row, dict):
                    canon_rows.append(
                        tuple(sorted((str(k), repr(v)) for k, v in row.items()))
                    )
                elif isinstance(row, (list, tuple)):
                    canon_rows.append(tuple(repr(v) for v in row))
                else:
                    canon_rows.append(repr(row))
            return tuple(sorted(canon_rows))
        except Exception:
            return repr(rows)