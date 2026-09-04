"""Execution-guided repair loop: generate SQL greedily, execute it against the database, and feed every execution error (plus the failing query and schema) back to the solver for corrective regeneration, for up to three attempts total."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS0G0(SQLHarness):
    """Greedy text-to-SQL improved by an execution-error-driven repair loop."""

    MAX_ATTEMPTS = 3  # one initial greedy generation + up to two repair rounds
    SYSTEM = "You are an expert text-to-SQL engineer."

    # ---------------------------- helpers ---------------------------- #

    def _generate(self, prompt: str) -> str:
        """One greedy call to the frozen solver, normalized to a plain string."""
        out = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):  # tolerate batch-style returns
            out = out[0] if out else ""
        return "" if out is None else str(out)

    def _extract(self, text: str) -> str:
        """Pull a single SQL statement out of a model response ('' if none)."""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""
        sql = (sql or "").strip()
        while sql.endswith(";"):  # bare single statements execute most reliably
            sql = sql[:-1].rstrip()
        return sql

    def _run(self, sql: str) -> dict:
        """Execute a candidate query without ever raising."""
        try:
            return self.execute(sql)
        except Exception as exc:  # a crashing executor counts as a failed run
            return {"ok": False, "rows": [], "error": "executor raised: %s" % exc}

    def _schema_block(self) -> str:
        schema = getattr(self, "schema", None)
        if not schema or not str(schema).strip():
            return "(no schema provided)"
        return str(schema)

    # ---------------------------- prompts ---------------------------- #

    def _initial_prompt(self, question: str) -> str:
        return (
            "You are an expert text-to-SQL agent.\n\n"
            "Database schema:\n%s\n\n"
            "Question: %s\n\n"
            "Write a single SQLite query that answers the question, using only "
            "the tables and columns shown in the schema.\n"
            "Return exactly one query inside a