"""Wrap a frozen weak SQL solver with execution-feedback repair, regenerating up to two times on SQLite errors."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2Repair(SQLHarness):
    """P2P2C MinMax S2 Repair: prompt -> generate -> execute -> repair on failure.

    Control flow:
        1. Construct an initial prompt from the question and schema.
        2. Call self.llm(...) to obtain candidate SQL.
        3. Extract SQL via bridge.extract_sql(...).
        4. Execute with self.execute(sql).
        5. If execution fails, append the exact SQLite error to the conversation
           and regenerate. Repeat for up to 2 repairs total (3 attempts).
        6. Return the last SQL produced (whether it succeeded or not).
    """

    _SYSTEM = (
        "You are a careful Text-to-SQL assistant. Produce a single SQLite-compatible "
        "SQL statement that answers the user's question against the provided schema. "
        "Return ONLY the SQL statement (optionally inside a