"""Repair-loop harness: generate SQL greedily, execute it, and feed any database error back to the frozen solver for up to three corrective regenerations."""

# MECHANISM: repair

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G3(SQLHarness):
    """Text-to-SQL harness with an execution-driven repair loop.

    Control flow (a real change vs. a single greedy call):

      1. One greedy LLM call maps (schema, question) -> candidate SQL.
      2. The candidate is executed against the target database.
      3. On failure, the failed SQL, the exact database error message, and
         deterministic hints about any identifiers the error mentions that are
         absent from the schema are packed into a repair prompt, and the
         solver regenerates a corrected query.
      4. Steps 2-3 repeat up to ``MAX_REPAIRS`` times.  The first query that
         executes cleanly is returned; otherwise the last candidate is.
    """

    MAX_REPAIRS = 3

    SYSTEM = (
        "You are an expert SQL writer. Given a database schema and a question, "
        "you produce exactly one SQL query and nothing else - no prose, no "
        "markdown fences, no comments."
    )

    # Words that show up in DB error text but are never schema identifiers.
    _STOPWORDS = {
        "and", "are", "attempt", "column", "constraint", "database", "does",
        "empty", "error", "exist", "executor", "failed", "for", "from",
        "function", "group", "line", "malformed", "mismatch", "missing", "near",
        "no", "not", "operator", "order", "produced", "query", "raised",
        "response", "row", "rows", "select", "statement", "such", "syntax",
        "table", "the", "type", "unknown", "usage", "value", "values", "where",
        "while", "with",
    }

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        sql = self._generate(self._initial_prompt(question))
        history = []  # [(failed_sql, error_message), ...]

        for attempt in range(self.MAX_REPAIRS + 1):
            outcome = self._try_execute(sql)
            if outcome["ok"]:
                return sql

            history.append((sql or "", outcome["error"]))

            if attempt == self.MAX_REPAIRS:
                break  # repair budget exhausted

            repaired = self._generate(self._repair_prompt(question, history))
            if not repaired or repaired == sql:
                break  # model made no usable progress; more calls are wasted
            sql = repaired

        # Nothing ever executed cleanly: return the last candidate (or a
        # trivially valid statement if the model never produced one at all).
        return sql or "SELECT 1;"

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _generate(self, prompt: str) -> str:
        """One greedy LLM call -> cleaned SQL string (possibly empty)."""
        text = self._call_llm(prompt)
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        if not isinstance(text, str):
            text = str(text)
        return self._normalize(bridge.extract_sql(text))

    def _call_llm(self, prompt: str):
        try:
            return self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        except TypeError:
            # Executor/solver variants with a narrower signature.
            return self.llm(prompt)

    def _try_execute(self, sql: str):
        """Run self.execute defensively; always return a well-formed dict."""
        if not sql:
            return {"ok": False, "rows": [], "error": "no SQL statement was produced"}
        try:
            result = self.execute(sql)
        except Exception as exc:  # executor raised instead of reporting
            return {"ok": False, "rows": [], "error": "executor raised: %r" % (exc,)}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "malformed executor response"}
        if result.get("ok"):
            return {"ok": True, "rows": result.get("rows", []), "error": ""}
        return {
            "ok": False,
            "rows": result.get("rows", []),
            "error": str(result.get("error") or "unknown execution error"),
        }

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write ONE SQL query that answers the question using only tables "
            "and columns that appear in the schema above.\n"
            "Output only the SQL query itself.\n"
            "SQL:"
        )

    def _repair_prompt(self, question: str, history) -> str:
        lines = [
            "Database schema:",
            str(self.schema),
            "",
            f"Question: {question}",
            "",
            "The following SQL attempts failed to execute against the database:",
        ]
        for i, (bad_sql, err) in enumerate(history, 1):
            lines.append(f"Attempt {i}:")
            lines.append(f"SQL: {bad_sql or '<no SQL produced>'}")
            lines.append(f"Error: {err}")

        hints = self._schema_hints(history[-1][1])
        if hints:
            lines.append("")
            lines.append(hints)

        lines += [
            "",
            "Write ONE corrected SQL query that answers the question and runs "
            "without errors. Fix every reported problem (unknown tables or "
            "columns, syntax, type mismatches, ...) and do not repeat a "
            "previous failed query.",
            "Output only the SQL query itself.",
            "SQL:",
        ]
        return "\n".join(lines)

    def _schema_hints(self, error: str) -> str:
        """Flag identifiers named in the error that never appear in the schema."""
        schema_l = (self.schema or "").lower()
        missing = []
        for word in dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", error or "")):
            lw = word.lower()
            if len(lw) < 3 or lw in self._STOPWORDS:
                continue
            if lw not in schema_l and word not in missing:
                missing.append(word)
        if not missing:
            return ""
        return (
            "Note: the schema contains no identifier matching: "
            + ", ".join(missing)
            + ". Re-check the exact table and column names in the schema above."
        )

    @staticmethod
    def _normalize(sql) -> str:
        if not sql:
            return ""
        s = str(sql).strip().strip("`").strip()
        while s.endswith(";"):
            s = s[:-1].rstrip()
        return s.strip()