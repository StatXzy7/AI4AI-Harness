"""Execute-and-repair loop: each generated query is run against the frozen database and the exact SQLite error message is fed back to the solver for up to three corrective regenerations, returning the first query that executes cleanly."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

_READ_ONLY_PREFIXES = ("select", "with")


class P2P2AGlmS2G1(SQLHarness):
    """Greedy generation plus an execution-feedback repair loop.

    Control flow (a real change over a single greedy call):

        sql_0        = LLM(schema, question)                      # greedy
        ok_i, err_i  = execute(sql_i)                             # real DB run
        sql_{i+1}    = LLM(schema, question, sql_0..i, err_0..i)  # repair

    The failing query *and the concrete database error string* are replayed to
    the frozen solver, which regenerates a corrected query. The first query
    whose execution returns ok wins; if the repair budget is exhausted, the
    most recent attempt is returned as a best effort. Queries that are not a
    single read-only SELECT are rejected before execution and fed back through
    the same repair channel.
    """

    MAX_REPAIRS = 3  # extra LLM calls after the initial greedy one

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. You answer with exactly one "
        "read-only SQL query and nothing else."
    )

    INITIAL_PROMPT = """Database schema:
{schema}

Question: {question}

Write ONE SQLite SELECT statement (a WITH ... SELECT CTE is allowed) that
answers the question using only the tables and columns shown above.
Output rules:
- Output exactly one query, inside a single