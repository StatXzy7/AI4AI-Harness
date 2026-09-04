"""Greedy SQL generation wrapped in a bounded repair loop: every candidate query is executed and each SQLite error is fed back to the frozen solver for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G7(SQLHarness):
    """Text-to-SQL harness with an execution-feedback repair loop.

    Control flow (a real change over a single greedy call):

      1. One greedy generation (temperature 0.0) produces a candidate query.
      2. The candidate is statically validated, then executed on the database.
      3. If validation or execution fails, the failed query together with the
         *verbatim* error message is fed back into a repair prompt and the
         solver regenerates a corrected query (slight temperature, so repairs
         can escape a deterministic repeat of the same mistake).
      4. Steps 2-3 repeat up to ``MAX_ATTEMPTS`` total LLM calls.
      5. The first query that executes cleanly is returned; if nothing ever
         executes cleanly, the last non-empty candidate is returned instead.

    Extra guards that keep the loop honest:
      * a query identical to an already-failed one is rejected without
        burning an execution, with an explicit "write something different"
        error fed back;
      * the repair prompt always shows the *entire* failure history, so the
        solver cannot quietly re-commit an earlier mistake;
      * non-SELECT / multi-statement outputs are caught before execution and
        reported as errors, so they enter the same feedback path.
    """

    MAX_ATTEMPTS = 4           # 1 greedy generation + up to 3 repairs
    REPAIR_TEMPERATURE = 0.3   # small randomness so repairs can escape repeats
    ALLOWED_PREFIXES = ("select", "with")

    # ------------------------------------------------------------------ #
    # prompting
    # ------------------------------------------------------------------ #
    @property
    def _schema_text(self) -> str:
        s = getattr(self, "schema", None)
        return s if isinstance(s, str) else ("" if s is None else str(s))

    def _system(self) -> str:
        return (
            "You are an expert SQLite data analyst. Given a database schema "
            "and a natural-language question, you write exactly one read-only "
            "SQLite query that answers it."
        )

    def _first_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self._schema_text}\n\n"
            f"Question:\n{question}\n\n"
            "Rules:\n"
            "- Output exactly one SQLite query and nothing else.\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- The query must be a single SELECT (or WITH ... SELECT) statement.\n"
            "- No prose, no comments, no markdown fences.\n\n"
            "SQL:"
        )

    def _repair_prompt(self, question: str, history) -> str:
        parts = [
            "Database schema:",
            self._schema_text,
            "",
            f"Question:\n{question}",
            "",
            "Your previous attempts were rejected. Each attempt is shown "
            "together with the exact error it produced:",
            "",
        ]
        for idx, (sql, err) in enumerate(history, 1):
            shown = sql if sql.strip() else "(no SQL could be extracted)"
            parts.append(f"Attempt {idx}:")
            parts.append(shown)
            parts.append(f"Error: {err}")
            parts.append("")
        parts.append(
            "Write ONE corrected SQLite query that fixes every error above. "
            "It must differ from all previous attempts, use only tables and "
            "columns from the schema, and be a single SELECT (or WITH ... "
            "SELECT) statement. Output only the query.\n\nSQL:"
        )
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _generate(self, prompt: str, temperature: float) -> str:
        out = self.llm(prompt, system=self._system(),
                       temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    @staticmethod
    def _tidy(sql) -> str:
        """Normalise an extracted query: drop fences / language tags and any
        trailing semicolon."""
        sql = (sql or "").strip() if isinstance(sql, str) else ""
        if not sql:
            return ""
        if "