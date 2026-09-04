"""A repair-loop harness that executes each candidate query and feeds execution errors back to the LLM for bounded regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS0G6(SQLHarness):
    """Generate SQL greedily, execute it, and on failure re-prompt the LLM with the
    failing SQL plus the database error message, repeating up to MAX_ATTEMPTS times."""

    MAX_ATTEMPTS = 4

    SYSTEM = (
        "You are an expert Text-to-SQL engine. Given a database schema and a "
        "natural-language question, produce exactly one valid SQL query that "
        "answers the question. Output only the SQL, with no explanation, no "
        "markdown fences, and no commentary."
    )

    def _generate(self, prompt: str, temperature: float) -> str:
        """Call the frozen LLM and normalize the return value to a plain string."""
        out = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    def _extract(self, text: str) -> str:
        """Pull SQL out of the raw model output, falling back to the stripped text."""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""
        if not sql:
            sql = text.strip()
        return sql.strip()

    def solve(self, question: str) -> str:
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question using only the "
            "tables and columns shown in the schema."
        )

        failures = []          # list of (failed_sql, error_message)
        last_sql = ""
        last_raw = ""

        for attempt in range(self.MAX_ATTEMPTS):
            if attempt == 0:
                prompt = base_prompt
                temperature = 0.0
            else:
                history = "\n\n".join(
                    f"Failed attempt {i + 1}:\n{bad_sql}\nDatabase error: {err}"
                    for i, (bad_sql, err) in enumerate(failures)
                )
                prompt = (
                    f"{base_prompt}\n\n"
                    "The previous quer"
                    f"{'y was' if len(failures) == 1 else 'ies were'} rejected by "
                    "the database engine:\n\n"
                    f"{history}\n\n"
                    "Diagnose the cause of the error(s) and return one corrected "
                    "SQL query. Do not repeat any of the failed statements."
                )
                # Escalating temperature gives the frozen model a chance to escape
                # the failing mode instead of deterministically repeating it.
                temperature = min(0.2 + 0.2 * (attempt - 1), 0.6)

            raw = self._generate(prompt, temperature)
            last_raw = raw
            candidate = self._extract(raw)

            if not candidate:
                failures.append(("<empty>", "model produced no extractable SQL"))
                continue

            last_sql = candidate
            result = self.execute(candidate)

            if result.get("ok"):
                return candidate

            failures.append((candidate, str(result.get("error", "unknown execution error"))))

        # All attempts exhausted: return the best artifact we have rather than nothing.
        return last_sql if last_sql else last_raw.strip()