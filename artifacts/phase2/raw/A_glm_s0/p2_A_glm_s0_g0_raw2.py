"""Execute-then-repair: a greedy SQL draft is executed against the database, and every execution error is fed back to the frozen solver to drive up to two corrective regenerations."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS0G0(SQLHarness):
    """Control flow: greedy draft -> execute -> (on error) regenerate with the
    database error message appended to the prompt, up to MAX_REPAIRS times."""

    MAX_REPAIRS = 2  # 1 initial generation + at most 2 error-driven repairs

    SYSTEM_PROMPT = (
        "You are an expert SQLite text-to-SQL engine. "
        "Always answer with exactly one SQLite SELECT query and nothing else."
    )

    # ------------------------------------------------------------------ helpers

    def _schema_text(self) -> str:
        schema = getattr(self, "schema", None)
        if schema is None:
            return "(no schema provided)"
        if not isinstance(schema, str):
            schema = str(schema)
        schema = schema.strip()
        return schema if schema else "(no schema provided)"

    @staticmethod
    def _clean(sql) -> str:
        """Normalise an extracted query: strip whitespace and trailing semicolons."""
        if not sql or not isinstance(sql, str):
            return ""
        sql = sql.strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    def _generate(self, prompt: str) -> str:
        """One greedy call to the frozen solver -> cleaned SQL ('' if nothing extracted)."""
        try:
            text = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        except TypeError:
            # Solver signatures that reject the keyword arguments.
            text = self.llm(prompt)
        if text is None:
            return ""
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        if not isinstance(text, str):
            text = str(text)
        try:
            return self._clean(bridge.extract_sql(text))
        except Exception:
            return ""

    def _execute(self, sql: str) -> dict:
        """Run a query and never raise: a crash is reported as an ordinary execution error."""
        try:
            outcome = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": f"execution raised: {exc}"}
        if isinstance(outcome, dict):
            return outcome
        return {"ok": bool(outcome), "rows": [], "error": "" if outcome else "execution failed"}

    # ------------------------------------------------------------------ prompts

    def _first_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self._schema_text()}\n\n"
            f"Question: {question}\n\n"
            "Task: write one SQLite SELECT query that answers the question.\n"
            "Rules:\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- Spell table and column names exactly as the schema does.\n"
            "- Return the query inside a