"""Repair-loop harness: generate SQL, execute it, and feed execution errors (or empty results) back to the LLM for iterative regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G6(SQLHarness):
    """Generates SQL greedily, executes it, and on failure feeds the SQLite
    error message (or a zero-row warning) back into the prompt, regenerating
    until the query executes and returns rows, or the attempt budget is spent.
    """

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite Text-to-SQL assistant. Given a database "
            "schema and a natural-language question, output exactly one valid "
            "SQLite SQL query that answers the question. Output only the SQL."
        )
        base_prompt = (
            "Database schema:\n" + str(self.schema) +
            "\n\nQuestion: " + question +
            "\n\nWrite the SQL query."
        )

        feedback = ""
        last_sql = ""
        last_error = ""

        for attempt in range(self.MAX_ATTEMPTS):
            prompt = base_prompt if not feedback else base_prompt + "\n\n" + feedback
            # Greedy first try; small temperature on retries to escape a frozen
            # decoder repeating the identical failing query.
            temperature = 0.0 if attempt == 0 else 0.3

            raw = self.llm(prompt, system=system, temperature=temperature, n=1)
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""
            sql = bridge.extract_sql(str(raw)).strip()

            if not sql:
                feedback = (
                    "Your previous response contained no extractable SQL query. "
                    "Respond with only the SQL query, nothing else."
                )
                continue

            if sql == last_sql and attempt > 0:
                # Identical retry with identical failure: nudge the decoder off
                # this fixed point before executing again.
                feedback = (
                    "The following SQL is wrong and repeating it will not help:\n"
                    + sql + "\nError: " + last_error +
                    "\nWrite a DIFFERENT, corrected query. Re-check table/column "
                    "names against the schema."
                )
                last_sql = sql
                continue

            result = self.execute(sql)
            last_sql = sql

            if result.get("ok"):
                rows = result.get("rows") or []
                if rows:
                    return sql
                last_error = "query returned zero rows"
                feedback = (
                    "The following SQL executed successfully but returned ZERO "
                    "rows:\n" + sql +
                    "\nRe-check join conditions, WHERE filters, and the exact "
                    "spelling/casing of literal values against the schema. Write "
                    "a corrected query that returns the requested data."
                )
            else:
                last_error = str(result.get("error", "unknown error"))
                feedback = (
                    "The following SQL failed to execute:\n" + sql +
                    "\nSQLite error: " + last_error +
                    "\nFix the query using only tables and columns present in the "
                    "schema, and output only the corrected SQL."
                )

        return last_sql if last_sql else "SELECT 1"