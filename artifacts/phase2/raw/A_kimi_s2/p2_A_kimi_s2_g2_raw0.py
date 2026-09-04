"""Execution-feedback repair harness: draft SQL greedily, execute it, and feed errors or suspicious empty results back to the LLM for regeneration until the query runs."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G2(SQLHarness):
    """Text-to-SQL harness with an execution-feedback repair loop.

    Control flow:
      1. Ask the frozen solver for a greedy (temperature 0) SQL draft.
      2. Execute the draft against the database.
      3. If it runs and returns rows, accept it immediately.
      4. Otherwise (SQLite error, or a suspicious zero-row result) append a
         description of the failure to the prompt and ask the solver to
         repair its own query. Repair rounds use a slightly higher
         temperature so a deterministically repeated mistake can be escaped.
      5. Results are memoised so an identical re-generated query is never
         executed twice; a repeated zero-row query is accepted as a
         legitimately empty answer instead of looping forever.
      6. When the attempt budget is exhausted, prefer the most recent query
         that at least executed successfully over one that crashes.
    """

    MAX_ATTEMPTS = 4

    SYSTEM_PROMPT = (
        "You are an expert SQLite text-to-SQL engine. Given a database schema "
        "and a natural-language question, you output exactly one valid SQLite "
        "SELECT query. You never output explanations, markdown fences, or "
        "anything other than the SQL itself."
    )

    def _base_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SELECT query that answers the question. "
            "Return only the SQL query."
        )

    def solve(self, question: str) -> str:
        base_prompt = self._base_prompt(question)
        prompt = base_prompt

        last_sql = ""
        executable_sql = ""  # most recent SQL that ran without an error
        cache = {}           # sql -> execution result, avoids re-running repeats
        zero_row_complaints = 0

        for attempt in range(self.MAX_ATTEMPTS):
            # Greedy first draft; nonzero temperature on repair rounds so a
            # deterministically repeated mistake can be escaped.
            temperature = 0.0 if attempt == 0 else 0.4
            response = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=temperature)
            sql = bridge.extract_sql(response)

            if not sql:
                prompt = (
                    base_prompt
                    + "\n\nYour previous reply contained no SQL query. "
                    "Respond with exactly one SQLite SELECT query and nothing else."
                )
                continue

            last_sql = sql

            result = cache.get(sql)
            if result is None:
                result = self.execute(sql)
                cache[sql] = result

            if result.get("ok"):
                executable_sql = sql
                rows = result.get("rows") or []
                if rows:
                    return sql
                # Zero rows: suspicious, but may be legitimate. Complain once;
                # if the solver's next draft still yields zero rows (or it
                # re-issues the very same query, hitting the cache), accept
                # the empty answer rather than loop forever.
                if zero_row_complaints >= 1:
                    return sql
                zero_row_complaints += 1
                feedback = (
                    "The query executed successfully but returned ZERO rows. "
                    "This often indicates an overly restrictive WHERE clause, a "
                    "wrong JOIN, or a string literal whose case/whitespace does "
                    "not match the stored values (consider LOWER(...) or LIKE)."
                )
            else:
                feedback = (
                    "SQLite raised this error: "
                    + str(result.get("error", "unknown error"))
                )

            prompt = (
                base_prompt
                + "\n\nYour previous SQL query was:\n"
                + sql
                + "\n\nProblem with that query:\n"
                + feedback
                + "\n\nRepair the query. Return only the corrected SQLite SQL "
                "query, with no explanation and no markdown."
            )

        # Budget exhausted: prefer a query that at least executes over one
        # that crashes.
        return executable_sql or last_sql