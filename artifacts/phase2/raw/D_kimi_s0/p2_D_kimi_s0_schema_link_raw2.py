"""Schema-linking Text-to-SQL harness: the LLM first identifies the tables/columns the question refers to, the schema is pruned to that linked subset in code, and SQL is then generated and execution-validated against only that subset."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS0SchemaLink(SQLHarness):
    """Two-stage pipeline: explicit schema linking, then SQL written against the linked subset."""

    _CREATE_RE = re.compile(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?([A-Za-z0-9_]+)["`\]]?',
        re.IGNORECASE,
    )
    _CONSTRAINT_STARTS = ("primary", "foreign", "unique", "check", "constraint", "key", "index")
    _MAX_REPAIRS = 2

    # ==================================================================
    # Entry point
    # ==================================================================
    def solve(self, question: str) -> str:
        schema = self.schema or ""

        # --- Stage 1: schema linking (which tables/columns are mentioned) ---
        blocks = self._split_schema(schema)
        linked_tables, linked_columns = self._link_schema(question, schema, blocks)

        # --- Stage 2: prune the schema to the linked subset (control flow) --
        linked_schema = self._build_linked_schema(blocks, linked_tables, linked_columns)
        if not linked_schema.strip():
            # Fallback: keep the full schema but prepend the linking decision as a hint.
            linked_schema = schema
            if linked_tables:
                hint = "-- Schema linking selected tables: " + ", ".join(sorted(linked_tables))
                col_bits = []
                for tbl, cols in sorted(linked_columns.items()):
                    if tbl != "*" and cols:
                        col_bits.append(tbl + "(" + ", ".join(sorted(cols)) + ")")
                if col_bits:
                    hint += "\n-- Schema linking selected columns: " + "; ".join(col_bits)
                linked_schema = hint + "\n" + schema

        # --- Stage 3: write SQL against the linked subset, repair on error ---
        return self._generate_and_repair(question, linked_schema)

    # ==================================================================
    # Stage 1: schema linking
    # ==================================================================
    def _link_schema(self, question, schema, blocks):
        """Ask the LLM which tables/columns the question needs; parse its answer."""
        if not blocks:
            return set(), {}
        known_tables = [name for name, _ in blocks if name]
        system = (
            "You are a schema-linking expert for Text-to-SQL. Given a database schema "
            "and a question, select exactly the tables and columns needed to answer "
            "the question -- nothing more, nothing less."
        )
        prompt = (
            "Database schema:\n" + schema + "\n\n"
            "Question: " + question + "\n\n"
            "Which tables and columns are required to answer this question? "
            "Include join keys and columns used in filters, grouping or aggregation.\n"
            "Answer in EXACTLY this format (two lines, no explanations, no markdown):\n"
            "TABLES: table1, table2\n"
            "COLUMNS: table1.col_a, table1.col_b, table2.col_c\n"
        )
        response = self._call_llm(prompt, system=system)
        tables, columns = self._parse_link_response(response)

        # Fallback: if the model ignored the format, scan for known table names.
        if not tables and response:
            lowered = response.lower()
            for name in known_tables:
                if re.search(r"\b" + re.escape(name.lower()) + r"\b", lowered):
                    tables.add(name.lower())
        return tables, columns

    def _parse_link_response(self, response):
        tables = set()
        columns = {}  # table(lower) -> {col(lower), ...}; "*" = unattributed columns
        for raw_line in (response or "").splitlines():
            line = raw_line.strip()
            if line.startswith("