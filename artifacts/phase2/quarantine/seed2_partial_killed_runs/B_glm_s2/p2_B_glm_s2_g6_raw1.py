"""Repair-loop harness: the weak solver's SQL is executed against the database, and any execution error or zero-row result is fed back into a repair prompt for up to three corrective regeneration rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G6(SQLHarness):
    """Execution-guided repair loop wrapped around the frozen weak solver.

    Control flow per question:
      1. One greedy generation call produces a candidate SQL string.
      2. The candidate is executed against the database with ``self.execute``.
      3. On failure (executor error, non-SELECT output, or zero rows) the
         failing SQL plus the concrete failure message is placed into a repair
         prompt and the solver regenerates the query.  The repair temperature
         ramps (0.0 -> 0.3 -> 0.6) so deterministic failure loops can be
         escaped; an unchanged output stalls the loop.
      4. At most three repair rounds run.  The first query that executes and
         returns rows is returned; otherwise the first query that merely
         executes; otherwise the first candidate.
    """

    MAX_ATTEMPTS = 4        # 1 initial generation + up to 3 repair rounds
    MAX_HISTORY = 3         # failed attempts echoed back in the repair prompt
    MAX_ERROR_CHARS = 300   # cap on executor error text injected into prompts

    SYSTEM_PROMPT = (
        "You are an expert data analyst who writes SQLite queries. "
        "Always answer with exactly one SQL SELECT statement and nothing "
        "else: no explanation, no markdown fences, no comments."
    )

    # ------------------------------------------------------------------
    # public entry point
    # ------------------------------------------------------------------

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        schema = getattr(self, "schema", "") or ""

        candidates = []   # [(sql, outcome), ...] in generation order
        history = []      # [(sql, feedback), ...] -- failures only
        nudged_empty = False

        sql = self._generate_initial(question, schema)

        for attempt in range(self.MAX_ATTEMPTS):
            outcome = self._safe_execute(sql)
            candidates.append((sql, outcome))

            if outcome["ok"] and outcome["n_rows"] > 0:
                break                                   # success
            if attempt == self.MAX_ATTEMPTS - 1:
                break                                   # out of budget

            if not outcome["ok"]:
                feedback = "Execution failed: %s" % (
                    outcome["error"] or "unknown error")
            elif not nudged_empty:
                # Soft failure: valid SQL but zero rows, usually a wrong
                # column, join key or filter.  Give exactly one nudge.
                nudged_empty = True
                feedback = (
                    "The query executed without error but returned 0 rows. "
                    "Re-check table names, column names, join keys and WHERE "
                    "filters against the schema. If 0 rows is genuinely the "
                    "correct answer, repeat the same query unchanged."
                )
            else:
                break   # one nudge per question; keep the valid query

            history.append((sql, feedback))

            temperature = 0.0 if attempt == 0 else min(0.6, 0.3 * attempt)
            repaired = self._generate_repair(
                question, schema, history, temperature)

            if not repaired or self._normalize(repaired) == self._normalize(sql):
                break   # stalled: the solver cannot improve on this attempt
            sql = repaired

        return self._select_best(candidates)

    # ------------------------------------------------------------------
    # generation stages
    # ------------------------------------------------------------------

    def _generate_initial(self, question: str, schema: str) -> str:
        prompt = (
            "Database schema:\n"
            f"{schema}\n\n"
            "Task: write one SQLite SQL query that answers the question below.\n\n"
            f"Question: {question}\n\n"
            "Requirements:\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- SQLite dialect: use LIMIT (never TOP), single-quote string literals.\n"
            "- Output exactly one SQL SELECT statement and nothing else.\n\n"
            "SQL:\n"
        )
        return self._extract_sql(self._call(prompt, 0.0))

    def _generate_repair(self, question: str, schema: str,
                         history, temperature: float) -> str:
        blocks = []
        for idx, (failed_sql, feedback) in enumerate(
                history[-self.MAX_HISTORY:], start=1):
            blocks.append(f"Attempt {idx}:")
            blocks.append(
                f"SQL: {failed_sql if failed_sql else '(no SQL produced)'}")
            blocks.append(f"Result: {feedback}")
            blocks.append("")
        history_block = "\n".join(blocks).strip()

        prompt = (
            "Database schema:\n"
            f"{schema}\n\n"
            "Task: write one SQLite SQL query that answers the question below.\n\n"
            f"Question: {question}\n\n"
            "Previous attempts failed as follows:\n"
            f"{history_block}\n\n"
            "Fix the most recent attempt, paying close attention to why it failed.\n"
            "Requirements:\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- SQLite dialect: use LIMIT (never TOP), single-quote string literals.\n"
            "- Output exactly one corrected SQL SELECT statement and nothing else.\n\n"
            "SQL:\n"
        )
        return self._extract_sql(self._call(prompt, temperature))

    # ------------------------------------------------------------------
    # low-level helpers
    # ------------------------------------------------------------------

    def _call(self, prompt: str, temperature: float) -> str:
        try:
            out = self.llm(prompt, system=self.SYSTEM_PROMPT,
                           temperature=temperature, n=1)
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return "" if out is None else str(out)

    def _extract_sql(self, text: str) -> str:
        sql = ""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""
        sql = (sql or "").strip()
        if not sql:
            # Fall back to the raw output; if it is not valid SQL the
            # execution feedback will steer the next repair round.
            sql = (text or "").strip()
        return sql

    def _safe_execute(self, sql: str) -> dict:
        sql = (sql or "").strip()
        if not sql:
            return {"ok": False, "n_rows": 0,
                    "error": "the solver produced no SQL statement"}
        lowered = sql.lower()
        if "select" not in lowered and "with" not in lowered:
            # Never send non-read statements (or prose) to the executor.
            return {"ok": False, "n_rows": 0,
                    "error": "the output is not a SQL SELECT statement"}
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "n_rows": 0,
                    "error": "executor raised %s: %s" % (
                        type(exc).__name__, exc)}
        if not isinstance(result, dict):
            return {"ok": False, "n_rows": 0,
                    "error": "executor returned %r instead of a result dict" % (
                        result,)}
        ok = bool(result.get("ok"))
        rows = result.get("rows")
        if not isinstance(rows, (list, tuple)):
            rows = []
        error = str(result.get("error") or "").strip()
        if not ok and not error:
            error = "execution failed (executor gave no error message)"
        return {"ok": ok, "n_rows": len(rows),
                "error": error[: self.MAX_ERROR_CHARS]}

    def _select_best(self, candidates) -> str:
        """First candidate with rows > first executable candidate > first."""
        best_sql = ""
        best_score = -1
        for sql, outcome in candidates:
            if outcome["ok"] and outcome["n_rows"] > 0:
                score = 2
            elif outcome["ok"]:
                score = 1
            else:
                score = 0
            if score > best_score:
                best_score = score
                best_sql = sql
        return best_sql or "SELECT 1"

    @staticmethod
    def _normalize(sql: str) -> str:
        return " ".join((sql or "").split()).lower().rstrip(";").strip()