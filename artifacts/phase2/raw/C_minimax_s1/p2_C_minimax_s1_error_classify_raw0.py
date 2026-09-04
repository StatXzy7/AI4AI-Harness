"""Wraps a frozen text-to-SQL weak solver with an execute-classify-fix control loop that distinguishes syntax, schema, and semantic errors across up to two correction rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS1ErrorClassify(SQLHarness):
    # --- helpers -----------------------------------------------------------

    def _classify_error(self, err: str) -> str:
        """Map an execution error string to one of {syntax, schema, semantic}."""
        if not err:
            return "none"
        e = err.lower()
        # Syntax: parser / tokenization issues
        syntax_markers = (
            "syntax error", "syntax", "parse error", "unexpected",
            "token", "unterminated", "invalid input", "lexical",
        )
        # Schema: references to missing/unknown columns, tables, functions
        schema_markers = (
            "no such column", "no such table", "unknown column",
            "unknown table", "does not exist", "not found",
            "ambiguous column", "no such function", "function not found",
            "no such database", "schema", "relation does not exist",
        )
        # Semantic: type / logic / runtime data issues
        semantic_markers = (
            "type mismatch", "datatype mismatch", "cannot be cast",
            "division by zero", "out of range", "integer overflow",
            "constraint", "not null", "unique", "foreign key",
            "more than one row", "more than one", "subquery returns",
            "returned more than", "returned one row", "scalar",
            "operand", "operator", "group by", "order by",
            "too many rows", "no rows", "empty",
        )
        if any(m in e for m in syntax_markers):
            return "syntax"
        if any(m in e for m in schema_markers):
            return "schema"
        if any(m in e for m in semantic_markers):
            return "semantic"
        # Default: treat unknown runtime failures as semantic
        return "semantic"

    def _generate(self, prompt: str, system: str = "") -> str:
        """Call the frozen weak solver exactly once and extract SQL."""
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(raw)

    def _fix_prompt(self, kind: str, question: str, sql: str, err: str) -> str:
        """Build a strategy-specific correction prompt."""
        base = f"You previously produced the following SQL for the question.\n\nQuestion: {question}\n\nSQL: {sql}\n\nError: {err}\n\n"
        if kind == "syntax":
            instr = (
                "Fix the SQL SYNTAX only. Rewrite the query so it parses correctly. "
                "Pay attention to balanced parentheses, commas between SELECT items, "
                "quoted identifiers, and trailing semicolons. Do not change the intent."
            )
        elif kind == "schema":
            instr = (
                "Fix SCHEMA / REFERENCE errors. The query referenced a column, table, "
                "or function that does not exist. Re-read the schema below and replace "
                "any bad identifiers with the closest valid ones. Do not invent new tables."
            )
            base += f"\nSchema:\n{self.schema}\n\n"
        else:  # semantic
            instr = (
                "Fix SEMANTIC / LOGIC errors. The query runs but does not answer the "
                "question correctly. Re-check JOINs, GROUP BY, aggregations, WHERE "
                "filters, aliases, and subquery cardinality. Rewrite so the result "
                "answers the question."
            )
        return base + instr

    # --- main control flow -------------------------------------------------

    def solve(self, question: str) -> str:
        # Round 0: initial generation
        system = "You are a Text-to-SQL generator. Use only the provided schema."
        prompt = f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nReturn only the SQL."
        sql = self._generate(prompt, system=system)
        if not sql:
            return ""

        # Up to 2 correction rounds
        for _ in range(2):
            res = self.execute(sql)
            if res.get("ok"):
                return sql
            err = res.get("error", "") or ""
            kind = self._classify_error(err)

            # Strategy-specific fix
            fix_prompt = self._fix_prompt(kind, question, sql, err)
            new_sql = self._generate(fix_prompt, system=system)
            if not new_sql:
                # If solver returned nothing usable, stop and keep current sql
                return sql
            sql = new_sql

        # Final attempt: return best-effort SQL even if it still fails
        return sql