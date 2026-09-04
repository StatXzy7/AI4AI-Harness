"""Greedy SQL generation wrapped in an execution-feedback repair loop: every candidate query is executed and the engine's error message (or an empty result set) is fed back to the frozen solver to drive corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G5(SQLHarness):
    """Greedy generation + execution-driven repair loop.

    Instead of a single greedy call, the harness:
      1. generates one SQL query greedily (temperature 0),
      2. executes it against the live database,
      3. on failure, feeds the failing SQL plus the exact engine error back
         to the solver for a corrective regeneration; every regenerated
         candidate is executed before the next round, duplicate candidates
         are pruned so the loop always terminates, and at most
         MAX_REPAIR_ROUNDS repairs are attempted,
      4. on success-with-zero-rows, makes one cautious repair attempt that is
         kept only if the fix also executes cleanly and returns rows,
      5. returns the first cleanly executing SQL (or the last attempt if
         nothing ever executed).
    """

    MAX_REPAIR_ROUNDS = 3
    MAX_ERROR_CHARS = 500

    SYSTEM_PROMPT = (
        "You are an expert SQL writer. Given a database schema and a natural "
        "language question, reply with exactly one valid SQL query and nothing "
        "else."
    )

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        current = self._generate_sql(self._initial_prompt(question))
        seen = {current}
        failures = []  # accumulated (sql, error) execution feedback
        ok_result = None

        # ---- hard-error repair loop ---------------------------------- #
        for _ in range(self.MAX_REPAIR_ROUNDS + 1):
            result = self._safe_execute(current)
            if result["ok"]:
                ok_result = result
                break
            failures.append((current, result["error"]))
            if len(failures) > self.MAX_REPAIR_ROUNDS:
                break
            candidate = self._generate_sql(
                self._error_repair_prompt(question, failures)
            )
            if not candidate or candidate in seen:
                break  # solver is not making progress; stop early
            seen.add(candidate)
            current = candidate

        if ok_result is None:
            # Nothing ever executed cleanly: return the last attempt.
            return current or "SELECT 1"

        # ---- soft repair: executed fine but returned zero rows -------- #
        if not ok_result["rows"]:
            candidate = self._generate_sql(
                self._empty_repair_prompt(question, current)
            )
            if candidate and candidate != current:
                cand_result = self._safe_execute(candidate)
                if cand_result["ok"] and cand_result["rows"]:
                    current = candidate

        return current or "SELECT 1"

    # ------------------------------------------------------------------ #
    # prompt construction
    # ------------------------------------------------------------------ #

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write ONE SQL query that answers the question, using only the "
            "tables and columns shown in the schema.\n"
            "Reply with the SQL query only."
        )

    def _error_repair_prompt(self, question: str, failures) -> str:
        lines = [
            "Database schema:",
            self.schema,
            "",
            f"Question: {question}",
            "",
            "Previous attempts to answer this question failed to execute. "
            "The database reported:",
            "",
        ]
        for i, (sql, err) in enumerate(failures, start=1):
            lines.append(f"{i}. SQL: {sql or '(no SQL produced)'}")
            lines.append(f"   Error: {self._clip(err or 'unknown execution error')}")
            lines.append("")
        lines.append(
            "Rewrite the query so that it executes successfully and still "
            "answers the question. Fix the exact problem each error describes "
            "(unknown table or column, bad syntax, wrong quoting, type or "
            "aggregate misuse, and so on) and use only tables and columns from "
            "the schema.\n"
            "Reply with the corrected SQL query only."
        )
        return "\n".join(lines)

    def _empty_repair_prompt(self, question: str, sql: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "The following query executed without errors but returned zero "
            f"rows:\n{sql}\n\n"
            "An empty result usually means a literal value, join key, or "
            "filter condition does not match the actual data.\n"
            "Reconsider those choices and rewrite the query so that it returns "
            "the rows that answer the question.\n"
            "Reply with the corrected SQL query only."
        )

    def _clip(self, text: str) -> str:
        text = (text or "").strip().replace("\n", " ")
        if len(text) > self.MAX_ERROR_CHARS:
            text = text[: self.MAX_ERROR_CHARS].rstrip() + " ..."
        return text

    # ------------------------------------------------------------------ #
    # frozen-solver plumbing
    # ------------------------------------------------------------------ #

    def _generate_sql(self, prompt: str) -> str:
        text = self._call_llm(prompt)
        sql = bridge.extract_sql(text) if text else ""
        if not sql or not sql.strip():
            sql = text
        return self._normalize(sql)

    def _call_llm(self, prompt: str) -> str:
        out = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if isinstance(out, dict):
            out = out.get("text") or out.get("content") or out.get("response") or ""
        if out is None:
            return ""
        if not isinstance(out, str):
            out = str(out)
        return out.strip()

    @staticmethod
    def _normalize(sql: str) -> str:
        s = (sql or "").strip()
        if s.startswith("