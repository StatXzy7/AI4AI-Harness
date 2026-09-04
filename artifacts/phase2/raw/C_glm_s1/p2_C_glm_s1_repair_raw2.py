"""Harness that generates SQLite SQL for a question, executes it against the database, and whenever execution fails feeds the exact SQLite error message back to the model to regenerate a corrected query, retrying up to 2 times."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS1Repair(SQLHarness):
    """Weak-solver wrapper: initial generation + execution-error-driven repair
    (a maximum of 2 regeneration rounds after the first failed execution)."""

    name = "p2p2c_glm_s1_repair"

    # Maximum number of *regeneration* attempts after the initial attempt fails.
    MAX_REPAIRS = 2

    INITIAL_SYSTEM = (
        "You are an expert SQLite programmer. Using only the tables and columns "
        "defined in the provided schema, write exactly one SQLite SQL query that "
        "answers the user's question. Output only the SQL inside a