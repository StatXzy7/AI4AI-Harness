"""Repair-loop Text-to-SQL harness: generate SQL, execute it, and feed execution errors back to the LLM for iterative correction."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G1(SQLHarness):
    """Generate SQL, execute it, and loop the database error back into the prompt.

    Control flow:
      1. Greedy (temperature=0) generation of a candidate query.
      2. Execute the candidate against the database.
      3. On success, return immediately.
      4. On failure, build a repair prompt containing the faulty SQL and the
         exact database error, and regenerate.
      5. If the model repeats an already-failed query verbatim, skip execution,
         raise the temperature, and demand a structurally different query.
      6. After MAX_ATTEMPTS, return the last parseable candidate.
    """

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL assistant. Given a database schema "
            "and a question you write one correct SQLite query. Answer with "
            "the SQL query only: no explanations, no markdown fences."
        )
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite query that answers the question."
        )

        prompt = base_prompt
        temperature = 0.0
        last_sql = ""
        last_error = ""
        tried = set()

        for _ in range(self.MAX_ATTEMPTS):
            raw = self.llm(prompt, system=system, temperature=temperature)
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""
            sql = bridge.extract_sql(raw) or ""

            if not sql:
                # Unparseable reply: re-ask with a stricter instruction.
                prompt = (
                    base_prompt
                    + "\n\nYour previous reply contained no SQL query. "
                      "Respond with the SQL query only."
                )
                continue

            if sql in tried and last_error:
                # Exact repeat of a known-failing query: don't re-execute,
                # force exploration of a different formulation instead.
                temperature = min(1.0, temperature + 0.4)
                prompt = self._repair_prompt(question, sql, last_error, different=True)
                continue

            last_sql = sql
            outcome = self.execute(sql)
            if outcome.get("ok"):
                return sql

            tried.add(sql)
            last_error = outcome.get("error") or "unknown execution error"
            prompt = self._repair_prompt(question, sql, last_error, different=False)

        return last_sql

    def _repair_prompt(self, question: str, sql: str, error: str, different: bool) -> str:
        note = (
            "This exact query was already tried and failed; produce a "
            "structurally different query (different tables, joins, or "
            "predicates), not a cosmetic rewrite."
            if different
            else "Fix the query."
        )
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "The following SQL query failed to execute.\n"
            f"Faulty SQL:\n{sql}\n\n"
            f"Database error:\n{error}\n\n"
            f"{note} Check table and column names against the schema and use "
            "valid SQLite syntax. Respond with the corrected SQL query only, "
            "no explanations, no markdown fences."
        )