"""Repair-loop harness that executes each generated SQL query and feeds execution errors back to the LLM for bounded regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G0(SQLHarness):
    """Generate SQL greedily, execute it, and on failure regenerate with the
    execution error fed back into the prompt (bounded number of attempts)."""

    MAX_ATTEMPTS = 4

    SYSTEM = (
        "You are an expert SQLite text-to-SQL engine. Given a database schema "
        "and a natural-language question, output exactly one valid SQLite "
        "query. Output only the SQL: no markdown fences, no explanations."
    )

    def _call_llm(self, prompt: str, temperature: float = 0.0) -> str:
        out = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out or ""

    def _execute(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
            if isinstance(result, dict):
                return result
            return {"ok": False, "rows": [], "error": f"unexpected executor response: {result!r}"}
        except Exception as exc:
            return {"ok": False, "rows": [], "error": f"executor raised: {exc}"}

    def solve(self, question: str) -> str:
        failures = []   # (sql, error) history fed back into the repair prompt
        seen = set()    # exact SQL strings already executed and failed
        candidate = ""
        temperature = 0.0

        for _ in range(self.MAX_ATTEMPTS):
            if not failures:
                prompt = (
                    f"Database schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    "Write one SQLite query that answers the question. "
                    "Output only the SQL."
                )
            else:
                log = "\n\n".join(
                    f"--- Failed attempt {i + 1} ---\nSQL:\n{sql}\n"
                    f"Database execution error:\n{err}"
                    for i, (sql, err) in enumerate(failures)
                )
                prompt = (
                    f"Database schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    "The SQL attempts below were executed against the database "
                    "and failed. Read each execution error, identify the cause "
                    "(wrong table/column names, SQLite syntax, quoting, joins, "
                    "aggregation), then write a corrected query.\n\n"
                    f"{log}\n\n"
                    "Output only the corrected SQLite query."
                )

            raw = self._call_llm(prompt, temperature=temperature)
            temperature = 0.0  # reset; only a repeated failure re-enables sampling

            sql = bridge.extract_sql(raw) or (raw or "").strip()
            if not sql:
                failures.append(("<empty>", "model produced no SQL"))
                continue

            candidate = sql
            if sql in seen:
                failures.append((sql, "this exact query already failed; produce a different query"))
                temperature = 0.5  # diversify to escape the deterministic failure
                continue
            seen.add(sql)

            result = self._execute(sql)
            if result.get("ok"):
                return sql
            failures.append((sql, str(result.get("error", "unknown execution error"))[:600]))

        return candidate