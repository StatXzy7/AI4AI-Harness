"""Iterative repair harness: generate SQL, execute it, and feed any database error back into the prompt for regeneration until the query runs or the attempt budget is exhausted."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G4(SQLHarness):
    """Repair-loop harness.

    Control flow:
      1. Greedy-generate a candidate SQL query from schema + question.
      2. Execute it against the database.
      3. If execution fails, append the failing SQL and the exact database
         error message to the prompt and regenerate (with a small temperature
         bump to escape deterministic repetition of the same mistake).
      4. Stop on the first successfully executing query; otherwise return the
         last candidate as a best-effort fallback.
    """

    MAX_ATTEMPTS = 4

    def _build_base_prompt(self, question: str) -> str:
        return (
            "You are given the following database schema:\n"
            f"{self.schema}\n\n"
            "Write a single valid SQL query that answers this question:\n"
            f"{question}\n\n"
            "Rules:\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Output ONLY the SQL query: no explanation, no comments, "
            "no markdown fences.\n"
        )

    def solve(self, question: str) -> str:
        system = (
            "You are an expert text-to-SQL engine. You respond with exactly "
            "one SQL query and nothing else."
        )
        base_prompt = self._build_base_prompt(question)

        prompt = base_prompt
        candidate = ""
        seen_sql = set()

        for attempt in range(self.MAX_ATTEMPTS):
            # First attempt is strictly greedy; retries get a small
            # temperature bump so a deterministic re-generation does not
            # simply repeat the identical failing query.
            temperature = 0.0 if attempt == 0 else 0.4

            raw = self.llm(prompt, system=system, temperature=temperature, n=1)
            sql = bridge.extract_sql(raw)

            if not sql:
                # Extraction failed: treat it like an error and ask again.
                prompt = (
                    base_prompt
                    + "\nYour previous reply contained no extractable SQL "
                      "query. Reply with ONLY the SQL query.\n"
                )
                continue

            if sql in seen_sql:
                # Already executed this exact query and it failed; push the
                # model to try a structurally different formulation.
                prompt = (
                    base_prompt
                    + "\nThe following query was already tried and failed:\n"
                    + sql
                    + "\nDo NOT repeat it. Write a DIFFERENT correct query.\n"
                )
                continue

            seen_sql.add(sql)
            candidate = sql

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "unknown database error")
            prompt = (
                base_prompt
                + "\nYour previous SQL query failed to execute.\n"
                + "Previous SQL:\n"
                + sql
                + "\n\nDatabase error message:\n"
                + str(error)
                + "\n\nDiagnose the cause of this error (e.g. wrong table or "
                  "column names, bad joins, invalid syntax) and output ONLY "
                  "the corrected SQL query.\n"
            )

        # All attempts exhausted: return the last extracted candidate as a
        # best-effort answer rather than an empty string.
        return candidate