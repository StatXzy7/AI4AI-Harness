"""Plan-to-Pieces Decompose harness: breaks a question into ordered sub-questions, answers each via small LLM calls, then assembles the final SQL."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS1Decompose(SQLHarness):
    """
    Plan-to-Pieces Decompose (P2P2D) harness.

    Strategy (in control flow, not only in the prompt):
      1. Identify tables referenced in the question and confirm/rank them.
      2. Identify the columns and any computed fields (aggregates, expressions).
      3. Identify filtering predicates (WHERE conditions).
      4. Identify grouping / ordering / limits.
      5. Assemble the final SELECT statement from the piece answers.
    """

    # Step 1 system prompt
    _SYS_TABLES = (
        "You are an expert SQL schema analyzer. "
        "Given a natural language question and a database schema, "
        "identify the tables (and only the tables) needed to answer the question. "
        "Return a short numbered list of table names, no commentary."
    )

    # Step 2 system prompt
    _SYS_COLUMNS = (
        "You are an expert SQL schema analyst. "
        "Given a natural language question, the schema, and a list of target tables, "
        "identify every column referenced or computed (aggregates, expressions). "
        "Return a short bullet list of 'table.column -> purpose', no commentary."
    )

    # Step 3 system prompt
    _SYS_FILTERS = (
        "You are an expert SQL analyst. "
        "Given a natural language question, the schema, and the chosen tables/columns, "
        "identify the WHERE-clause filtering predicates in plain English bullets. "
        "No SQL yet."
    )

    # Step 4 system prompt
    _SYS_SHAPE = (
        "You are an expert SQL analyst. "
        "Given a natural language question, schema, tables, columns and filters, "
        "describe in plain English: grouping columns (GROUP BY), ordering (ORDER BY), "
        "limit/offset, and whether DISTINCT is needed. "
        "No SQL yet."
    )

    # Step 5 system prompt
    _SYS_ASSEMBLE = (
        "You are an expert SQL writer. "
        "Given a question, schema, and structured notes about tables, columns, filters, "
        "and shape (group/order/limit), write the final single SQL statement that answers "
        "the question. Output ONLY the SQL statement, nothing else."
    )

    def _ask(self, system: str, user: str) -> str:
        # Low temperature, single completion for deterministic decomposition.
        return self.llm(user, system=system, temperature=0.0, n=1)

    def solve(self, question: str) -> str:
        schema = self.schema

        # Step 1 - tables
        tables_text = self._ask(
            self._SYS_TABLES,
            f"Schema:\n{schema}\n\nQuestion: {question}\n\nTables needed:",
        )

        # Step 2 - columns
        columns_text = self._ask(
            self._SYS_COLUMNS,
            f"Schema:\n{schema}\n\nQuestion: {question}\n\n"
            f"Target tables:\n{tables_text}\n\nColumns needed:",
        )

        # Step 3 - filters
        filters_text = self._ask(
            self._SYS_FILTERS,
            f"Schema:\n{schema}\n\nQuestion: {question}\n\n"
            f"Target tables:\n{tables_text}\n\n"
            f"Columns:\n{columns_text}\n\nFilters:",
        )

        # Step 4 - shape
        shape_text = self._ask(
            self._SYS_SHAPE,
            f"Schema:\n{schema}\n\nQuestion: {question}\n\n"
            f"Target tables:\n{tables_text}\n\n"
            f"Columns:\n{columns_text}\n\n"
            f"Filters:\n{filters_text}\n\nShape:",
        )

        # Step 5 - assemble
        assembly_text = self._ask(
            self._SYS_ASSEMBLE,
            f"Schema:\n{schema}\n\nQuestion: {question}\n\n"
            f"Target tables:\n{tables_text}\n\n"
            f"Columns:\n{columns_text}\n\n"
            f"Filters:\n{filters_text}\n\n"
            f"Shape:\n{shape_text}\n\nSQL:",
        )

        # Extract a clean SQL string from the assembly answer.
        final_sql = bridge.extract_sql(assembly_text)

        # If extraction fails, fall back to the raw text trimmed.
        if not final_sql:
            final_sql = assembly_text.strip()

        # Light self-check: if execution is available and fails, retry assembly once
        # with the error message appended.
        exec_result = self.execute(final_sql)
        if not exec_result.get("ok", False):
            retry_text = self._ask(
                self._SYS_ASSEMBLE,
                f"Schema:\n{schema}\n\nQuestion: {question}\n\n"
                f"Target tables:\n{tables_text}\n\n"
                f"Columns:\n{columns_text}\n\n"
                f"Filters:\n{filters_text}\n\n"
                f"Shape:\n{shape_text}\n\n"
                f"Previous SQL error: {exec_result.get('error', 'unknown')}\n\n"
                f"Previous SQL: {final_sql}\n\nCorrected SQL:",
            )
            final_sql = bridge.extract_sql(retry_text) or retry_text.strip()

        return final_sql