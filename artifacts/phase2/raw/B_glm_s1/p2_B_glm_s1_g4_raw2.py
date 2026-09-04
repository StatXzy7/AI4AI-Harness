"""Repair-loop harness: greedily draft SQL, execute it, and feed the database error message back to the LLM for up to three corrective regenerations."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G4(SQLHarness):
    """Greedy draft followed by execution-feedback repair rounds.

    Control flow:
      1. One greedy (temperature 0.0) draft is generated and executed.
      2. If execution fails, the failing SQL plus the exact database error
         are appended to a repair prompt and the model regenerates.
      3. This repeats for up to MAX_ATTEMPTS total attempts; if the model
         deterministically repeats an already-failed query, the sampling
         temperature is bumped so the repair round can escape the loop.
      4. The first query that executes successfully is returned; otherwise
         the last non-empty draft is returned as a best effort.
    """

    MAX_ATTEMPTS = 4  # 1 initial greedy draft + up to 3 error-driven repairs

    def solve(self, question: str) -> str:
        schema = self.schema if self.schema is not None else ""

        system = (
            "You are an expert text-to-SQL translator. Given a database schema "
            "and a natural language question, produce exactly one SQLite query "
            "that answers the question. Use only tables and columns that appear "
            "in the schema. Respond with the SQL query and nothing else."
        )
        prompt = (
            "Database schema:\n"
            "%s\n\n"
            "Question: %s\n\n"
            "SQL query:"
        ) % (schema, question)

        temperature = 0.0
        seen = set()
        last_sql = ""

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            text = self._generate(prompt, system, temperature)
            sql = bridge.extract_sql(text) if text else ""
            if not isinstance(sql, str):
                sql = "" if sql is None else str(sql)
            sql = sql.strip()
            while sql.endswith(";"):
                sql = sql[:-1].strip()

            if sql:
                result = self._run(sql)
                ok = bool(result.get("ok"))
                error = str(result.get("error") or "query failed to execute")
            else:
                ok = False
                error = "no SQL query could be extracted from the model output"

            if ok:
                return sql

            if sql:
                last_sql = sql
                if sql in seen and attempt < self.MAX_ATTEMPTS:
                    # Deterministic repeat of a failed query: raise temperature
                    # so the next repair round can produce something new.
                    temperature = min(1.0, temperature + 0.4)
                seen.add(sql)

            if attempt < self.MAX_ATTEMPTS:
                prompt = (
                    "Database schema:\n"
                    "%s\n\n"
                    "Question: %s\n\n"
                    "Your previous SQL query failed to execute against the database.\n\n"
                    "Failed query:\n"
                    "%s\n\n"
                    "Database error:\n"
                    "%s\n\n"
                    "Write a corrected SQL query that executes successfully against "
                    "the schema. Re-check table names, column names, join keys, and "
                    "quoting. Respond with the corrected SQL query only."
                ) % (
                    schema,
                    question,
                    sql if sql else "(the model produced no query)",
                    error,
                )

        # Nothing executed cleanly; return the most recent non-empty draft,
        # or a trivially valid query as a last resort to keep the pipeline alive.
        return last_sql or "SELECT 1"

    def _generate(self, prompt, system, temperature):
        """Call the frozen LLM, tolerating narrower call signatures."""
        out = ""
        try:
            out = self.llm(prompt, system=system, temperature=temperature, n=1)
        except TypeError:
            try:
                out = self.llm(prompt, system=system, temperature=temperature)
            except TypeError:
                try:
                    out = self.llm(prompt, system=system)
                except TypeError:
                    out = self.llm(prompt)
        except Exception:
            out = ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if not isinstance(out, str):
            out = "" if out is None else str(out)
        return out

    def _run(self, sql):
        """Execute a query defensively; always return a dict-shaped result."""
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": "executor raised: %s" % (exc,)}
        if isinstance(result, dict):
            return result
        return {
            "ok": bool(getattr(result, "ok", False)),
            "rows": getattr(result, "rows", []),
            "error": str(getattr(result, "error", "unknown execution error")),
        }