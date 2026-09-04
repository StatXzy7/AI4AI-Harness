"""Two-stage control flow: a first LLM call links the question to the schema and emits a structured query-plan artifact, and a second LLM call compiles that plan into the final SQL."""

# MECHANISM: twostage

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS0G5(SQLHarness):
    """Plan-then-compile wrapper around the frozen weak solver.

    Stage 1 (planner): the LLM reads the schema plus the question and writes a
    structured query plan -- tables, columns, join conditions, literal filter
    values, aggregation, grouping, ordering, and known pitfalls. No SQL is
    written in this stage.

    Stage 2 (compiler): a second LLM call receives the schema, the question and
    the stage-1 plan artifact, and must translate the *plan* (not the raw
    question) into a single SQLite SELECT statement. The artifact is the only
    channel between the two stages.
    """

    PLAN_SYSTEM = (
        "You are a senior database analyst. You read a database schema and a "
        "natural-language question and you write a precise, terse execution "
        "plan for the query. You never write SQL."
    )

    SQL_SYSTEM = (
        "You are an expert SQLite programmer. You are given a question and an "
        "already-approved query plan. You translate the plan into exactly one "
        "correct SQLite SELECT statement and output nothing but SQL."
    )

    #: hard cap on the plan artifact so stage 2 cannot be flooded
    MAX_PLAN_CHARS = 4000

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return ""

        # ---- Stage 1: schema linking + planning  ->  plan artifact --------
        plan = self._plan(question)

        # ---- Stage 2: compile the plan artifact  ->  SQL ------------------
        raw = self._compile(question, plan)

        sql = bridge.extract_sql(raw)
        if not sql or not str(sql).strip():
            sql = self._fallback_extract(raw)
        return str(sql or "").strip()

    # ------------------------------------------------------------------ #
    # Stage 1 -- planner
    # ------------------------------------------------------------------ #
    def _plan(self, question: str) -> str:
        prompt = (
            "Database schema:\n"
            f"{self._schema()}\n\n"
            f"Question: {question}\n\n"
            "Write a query plan for this question. Do NOT write SQL. "
            "Use exactly these lines, in this order, each under 200 characters:\n"
            "TABLES: tables that must be read (comma separated)\n"
            "COLUMNS: table.column values that must be used, including join keys\n"
            "JOINS: the equi-join conditions connecting the tables, or NONE\n"
            "FILTERS: WHERE conditions, with literal values copied verbatim from the question, or NONE\n"
            "AGGREGATION: COUNT/SUM/MIN/MAX/AVG and its argument, or NONE\n"
            "GROUP_BY: grouping columns, or NONE\n"
            "ORDER_LIMIT: ordering columns/direction and any LIMIT, or NONE\n"
            "PITFALLS: value formats, quoting, case sensitivity, NULL handling or other traps\n"
        )
        plan = self._call(prompt, system=self.PLAN_SYSTEM).strip()
        if len(plan) > self.MAX_PLAN_CHARS:
            plan = plan[: self.MAX_PLAN_CHARS]
        return plan

    # ------------------------------------------------------------------ #
    # Stage 2 -- compiler (consumes the stage-1 artifact)
    # ------------------------------------------------------------------ #
    def _compile(self, question: str, plan: str) -> str:
        plan_block = plan.strip() or "(the analyst returned no plan; work from the schema alone)"
        prompt = (
            "Database schema:\n"
            f"{self._schema()}\n\n"
            f"Question: {question}\n\n"
            "A senior analyst already analysed this question and produced the "
            "query plan below. Follow the plan: it identifies the tables, "
            "columns, join conditions, literal filter values, aggregation, "
            "grouping and ordering.\n"
            "---------------- QUERY PLAN ----------------\n"
            f"{plan_block}\n"
            "---------------- END PLAN ----------------\n\n"
            "Write the single SQLite SELECT statement that implements this plan "
            "exactly. Use only tables and columns that exist in the schema, and "
            "copy literal values from the plan verbatim. Output only the SQL, "
            "wrapped in a