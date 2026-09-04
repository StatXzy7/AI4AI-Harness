"""Iteratively repairs a greedy SQL generation by executing it and feeding database error messages back into a repair prompt until it runs or attempts run out."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS1G0(SQLHarness):
    """Generate -> execute -> on error, feed the error back and regenerate.

    The first query is produced greedily (temperature 0). Every execution
    failure is appended to a failure history, and a repair prompt containing
    the schema, the question, and the full (sql, error) history is used to
    produce a corrected query. If the model gets stuck repeating the same
    broken SQL, the temperature is nudged upward to escape the loop. The
    first query that executes successfully is returned; otherwise the last
    candidate is returned as a best effort.
    """

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL translator. Given a database "
            "schema and a natural-language question, produce exactly one "
            "valid SQL query that answers the question. Output only the SQL "
            "query itself: no explanations, no markdown fences, no comments."
        )

        initial_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question."
        )

        sql = self._generate(initial_prompt, system, temperature=0.0)
        history = []  # list of (failed_sql, error_message)

        for attempt in range(self.MAX_ATTEMPTS):
            if not sql:
                # Extraction produced nothing usable; regenerate from scratch.
                sql = self._generate(initial_prompt, system, temperature=0.2)
                continue

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = str(result.get("error", "unknown execution error"))
            history.append((sql, error))

            if attempt == self.MAX_ATTEMPTS - 1:
                break  # No attempts left; fall through to best-effort return.

            repair_prompt = self._build_repair_prompt(question, history)
            # Escalate temperature if the previous repair merely repeated the
            # same broken query, to escape a deterministic failure loop.
            temperature = 0.0
            if history and len(history) >= 2 and history[-1][0].strip() == history[-2][0].strip():
                temperature = 0.4
            elif any(prev.strip() == sql.strip() for prev, _ in history[:-1]):
                temperature = 0.4

            repaired = self._generate(repair_prompt, system, temperature=temperature)
            if repaired:
                sql = repaired

        return sql

    def _generate(self, prompt: str, system: str, temperature: float) -> str:
        """Call the frozen LLM and extract a SQL string from its response."""
        response = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""
        sql = bridge.extract_sql(response)
        if not sql:
            sql = response
        return sql.strip() if isinstance(sql, str) else ""

    def _build_repair_prompt(self, question: str, history) -> str:
        """Construct a prompt that shows the model its failed SQL and the DB errors."""
        parts = [
            f"Database schema:\n{self.schema}\n",
            f"Question: {question}\n",
            "The following SQL queries were tried and each failed to execute. "
            "Study the database error messages and produce a corrected query "
            "that avoids every one of these mistakes.",
        ]
        for i, (bad_sql, error) in enumerate(history, start=1):
            parts.append(
                f"\nAttempt {i} SQL:\n{bad_sql}\n"
                f"Database error for attempt {i}:\n{error}"
            )
        parts.append(
            "\nNow write one corrected SQL query. Output only the SQL query."
        )
        return "\n".join(parts)