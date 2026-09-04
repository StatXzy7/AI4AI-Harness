"""Generate SQL greedily, execute it, and feed execution errors back to the LLM for iterative repair until the query runs."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

SYSTEM_PROMPT = (
    "You are an expert Text-to-SQL system. Given a database schema and a "
    "natural-language question, write a single SQL query that answers the "
    "question. Use only tables and columns that exist in the schema. Output "
    "only the SQL query, optionally inside a fenced code block."
)

GENERATE_PROMPT = """\
Database schema:
{schema}

Question: {question}

Write one SQL query that answers the question. Output only the SQL."""

REPAIR_PROMPT = """\
Database schema:
{schema}

Question: {question}

The following SQL query was executed against this database and FAILED.

Failed SQL:
{sql}

Execution error:
{error}

Diagnose the cause of the error (e.g., nonexistent table or column names, bad
joins, syntax mistakes, wrong literals) and rewrite the query so that it
executes correctly and still answers the question. Output only the corrected
SQL query."""


class P2P2BKimiS1G4(SQLHarness):
    """Greedy Text-to-SQL with an execution-feedback repair loop.

    Improvement over a single greedy call: the generated SQL is actually run
    against the database; on failure, the error message is fed back to the
    LLM, which produces a repaired query. This repeats for a bounded number
    of attempts and returns the first query that executes successfully.
    """

    MAX_ATTEMPTS = 4  # 1 initial generation + up to 3 repair rounds

    def _to_sql(self, text: str) -> str:
        """Extract SQL from an LLM response, falling back to the raw text."""
        sql = bridge.extract_sql(text)
        return sql if sql and sql.strip() else text.strip()

    def solve(self, question: str) -> str:
        sql = self._to_sql(
            self.llm(
                GENERATE_PROMPT.format(schema=self.schema, question=question),
                system=SYSTEM_PROMPT,
                temperature=0.0,
            )
        )

        last_sql = sql
        for attempt in range(self.MAX_ATTEMPTS):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "unknown execution error")
            last_sql = sql
            if attempt == self.MAX_ATTEMPTS - 1:
                break  # out of repair budget; return best effort below

            repaired = self._to_sql(
                self.llm(
                    REPAIR_PROMPT.format(
                        schema=self.schema,
                        question=question,
                        sql=sql,
                        error=error,
                    ),
                    system=SYSTEM_PROMPT,
                    temperature=0.0,
                )
            )
            if not repaired or repaired == sql:
                break  # deterministic model produced no change; further repairs would repeat
            sql = repaired

        return last_sql