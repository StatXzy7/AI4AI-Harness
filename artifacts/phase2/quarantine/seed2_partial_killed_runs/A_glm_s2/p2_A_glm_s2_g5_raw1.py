"""Wraps the frozen solver in an execution-guided repair loop: each generated SQL query is executed against the real database, and any execution error is fed back verbatim to prompt up to four corrective regenerations, returning the first query that executes cleanly (or the original greedy query as a fallback)."""

# MECHANISM: repair

from typing import Any, Dict, List, Tuple

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2AGlmS2G5"]


class P2P2AGlmS2G5(SQLHarness):
    """Greedy generation followed by an execution-error-driven repair loop.

    Control flow (a real change over a single greedy call):

      1. One greedy LLM call turns (schema, question) into a first SQL
         candidate.
      2. The candidate is *executed* against the database via self.execute.
      3. If the database rejects it, the failing SQL together with the exact
         error string is appended to a repair prompt and the solver
         regenerates a corrected query.
      4. Steps 2-3 repeat, bounded by MAX_REPAIRS and de-duplicated so the
         solver cannot loop on the same broken query.  The first query that
         executes cleanly is returned; if nothing executes, the original
         greedy candidate is returned as the best-effort answer.
    """

    MAX_REPAIRS = 4           # corrective regenerations after the first failure
    RETRY_TEMPERATURE = 0.4   # diversity once a deterministic repair has failed

    SYSTEM_PROMPT = (
        "You are an expert SQL writer working against a SQLite database. "
        "Given a schema and a question, produce exactly one SQL query that "
        "answers the question. Use only tables and columns that appear in "
        "the schema. Respond with the SQL query only: no prose, no markdown "
        "fences, no explanation."
    )

    # ------------------------------------------------------------------ #
    # public entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        prompt = self._initial_prompt(question)

        # ---- first shot: a single greedy generation -------------------- #
        candidate = self._generate(prompt, temperature=0.0)
        if not candidate:
            # Degenerate output (empty / unparseable): one warmer retry.
            candidate = self._generate(prompt, temperature=self.RETRY_TEMPERATURE)
        if not candidate:
            return "SELECT 1;"  # the solver produced nothing usable at all

        fallback = candidate            # returned if every repair still fails
        seen = {self._norm(candidate)}  # queries already tried and failed
        history: List[Tuple[str, str]] = []  # [(failed_sql, error), ...]

        # ---- repair loop ---------------------------------------------- #
        # Up to MAX_REPAIRS + 1 executions: each failure (except the last)
        # triggers one corrective regeneration conditioned on the errors.
        for attempt in range(self.MAX_REPAIRS + 1):
            result = self._safe_execute(candidate)
            if result.get("ok"):
                return candidate         # clean execution: we are done

            if attempt == self.MAX_REPAIRS:
                break                    # repair budget exhausted

            error = str(result.get("error") or "").strip() or "query failed to execute"
            history.append((candidate, error))

            repaired = self._generate(
                self._repair_prompt(question, history),
                temperature=0.0 if attempt == 0 else self.RETRY_TEMPERATURE,
            )
            if not repaired:
                break                    # solver produced nothing usable
            if self._norm(repaired) in seen:
                break                    # solver is looping on a failed query
            seen.add(self._norm(repaired))
            candidate = repaired         # this repair gets executed next round

        return fallback

    # ------------------------------------------------------------------ #
    # prompt construction
    # ------------------------------------------------------------------ #

    def _schema_block(self) -> str:
        schema = str(getattr(self, "schema", "") or "").strip()
        return schema if schema else "(no schema provided)"

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self._schema_block()}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. "
            "Output only the SQL query."
        )

    def _repair_prompt(self, question: str, history: List[Tuple[str, str]]) -> str:
        parts = [
            "Database schema:",
            self._schema_block(),
            "",
            f"Question: {question}",
            "",
            "Your previous SQL queries failed to execute against the "
            "database. Each failed attempt is shown together with its "
            "exact database error:",
            "",
        ]
        for i, (sql, error) in enumerate(history, 1):
            parts.append(f"Attempt {i}:")
            parts.append(f"SQL: {sql}")
            parts.append(f"Error: {error}")
            parts.append("")
        parts.append(
            "Write a corrected SQL query that answers the question and "
            "avoids every error listed above. Re-check table names, column "
            "names, join conditions, quoting, and syntax; if a name you "
            "used is unknown, choose the closest match that actually "
            "appears in the schema. Output only the corrected SQL query."
        )
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # generation / extraction / execution helpers
    # ------------------------------------------------------------------ #

    def _generate(self, prompt: str, temperature: float) -> str:
        """Call the frozen solver and reduce its output to a clean SQL string."""
        raw = self._call_llm(prompt, temperature)
        text = self._as_text(raw)
        if not text:
            return ""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = text
        if not sql or not str(sql).strip():
            sql = text  # extractor found nothing; fall back to the raw text
        return self._clean(str(sql))

    def _call_llm(self, prompt: str, temperature: float) -> Any:
        """Invoke self.llm with the documented signature, tolerating stricter ones."""
        variants = (
            {"system": self.SYSTEM_PROMPT, "temperature": temperature, "n": 1},
            {"system": self.SYSTEM_PROMPT, "temperature": temperature},
            {"system": self.SYSTEM_PROMPT},
            {},
        )
        for kwargs in variants:
            try:
                return self.llm(prompt, **kwargs)
            except Exception:
                continue
        return None

    def _safe_execute(self, sql: str) -> Dict[str, Any]:
        """Execute SQL without ever letting an exception escape the loop."""
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": f"execution raised: {exc}"}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "execution returned no result"}
        return result

    # ------------------------------------------------------------------ #
    # small utilities
    # ------------------------------------------------------------------ #

    @staticmethod
    def _as_text(raw: Any) -> str:
        """Coerce whatever the LLM wrapper returns into plain text."""
        if raw is None:
            return ""
        if isinstance(raw, (list, tuple)):
            if not raw:
                return ""
            raw = raw[0]
        if isinstance(raw, dict):
            raw = raw.get("text") or raw.get("content") or raw.get("output") or ""
        if not isinstance(raw, str):
            return ""
        return raw.strip()

    @staticmethod
    def _clean(sql: str) -> str:
        """Normalize whitespace, stray markdown fences, and trailing ';'.
        The very same normalization is used for execution and for the final
        answer, so what we test is exactly what we return."""
        sql = (sql or "").strip()
        if sql.startswith("