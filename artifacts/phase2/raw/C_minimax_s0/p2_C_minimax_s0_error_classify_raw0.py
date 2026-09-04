"""P2P2CMinimaxS0ErrorClassify wraps a frozen weak solver and applies class-specific recovery after syntax, schema, or semantic failures, up to 2 repair rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS0ErrorClassify(SQLHarness):
    MAX_ROUNDS = 2

    def solve(self, question: str) -> str:
        final_sql = ""
        prompt = self._build_initial_prompt(question)
        system = (
            "You are a Text-to-SQL assistant. Given a schema and a natural "
            "language question, produce exactly one valid SQL query. "
            "Respond with only the SQL (no markdown, no commentary)."
        )

        for round_idx in range(self.MAX_ROUNDS + 1):
            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            sql = bridge.extract_sql(raw) if raw else ""
            if not sql:
                sql = ""
                final_sql = sql
                break

            result = self.execute(sql)
            final_sql = sql

            if result.get("ok", False):
                # Sanity-check that we got something non-empty
                if result.get("rows") is not None or result.get("error") == "":
                    return sql

            if round_idx >= self.MAX_ROUNDS:
                break

            err = (result.get("error") or "").strip()
            failure_class = self._classify_failure(err, sql, question)
            prompt = self._build_repair_prompt(
                question, sql, err, failure_class, round_idx
            )

        return final_sql

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #
    def _build_initial_prompt(self, question: str) -> str:
        return (
            "### Schema\n"
            f"{self.schema}\n\n"
            "### Question\n"
            f"{question}\n\n"
            "### SQL\n"
        )

    def _build_repair_prompt(
        self,
        question: str,
        sql: str,
        error: str,
        failure_class: str,
        round_idx: int,
    ) -> str:
        strategy_text = self._strategy_instruction(failure_class)
        return (
            f"### Schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            f"### Previous SQL\n{sql}\n\n"
            f"### Execution Error\n{error}\n\n"
            f"### Diagnosis\n"
            f"The previous query failed with a **{failure_class}** error.\n\n"
            f"### Repair Strategy\n{strategy_text}\n\n"
            "### Corrected SQL\n"
        )

    def _strategy_instruction(self, failure_class: str) -> str:
        if failure_class == "syntax":
            return (
                "Re-check the SQL for syntax errors only. Make sure parentheses "
                "are balanced, every keyword is valid, strings are properly "
                "quoted, and there is a terminating semicolon if required. "
                "Do not change table or column names."
            )
        if failure_class == "schema":
            return (
                "The error is caused by referencing a table or column that "
                "does not exist in the schema. Inspect the schema carefully, "
                "fix every table/column name to match it exactly, and only "
                "use identifiers that appear in the schema."
            )
        if failure_class == "semantics":
            return (
                "The SQL parsed and referenced valid objects, but it does not "
                "answer the question correctly. Rewrite the query so that it "
                "matches the intent of the question: check joins, WHERE clauses, "
                "GROUP BY / aggregate arguments, DISTINCT usage, and ordering. "
                "Keep the structure minimal and faithful to the question."
            )
        return (
            "Re-examine the schema and the question, and produce a corrected "
            "SQL query."
        )

    # ------------------------------------------------------------------ #
    # Failure classification
    # ------------------------------------------------------------------ #
    def _classify_failure(self, error: str, sql: str, question: str) -> str:
        e = error.lower()
        q = question.lower()

        # 1. Syntax errors come from the parser/engine before table lookup.
        syntax_markers = (
            "syntax error",
            "near ",
            "unexpected",
            "parse error",
            "token",
            "missing",
            "unterminated",
            "mismatched",
            "unmatched",
        )
        if any(m in e for m in syntax_markers):
            return "syntax"

        # 2. Schema errors: unknown / ambiguous / non-existent identifiers.
        schema_markers = (
            "no such table",
            "no such column",
            "unknown column",
            "unknown table",
            "does not exist",
            "doesn't exist",
            "not found",
            "ambiguous",
            "invalid identifier",
            "undefined",
            "table not found",
            "column not found",
            "field not found",
        )
        if any(m in e for m in schema_markers):
            return "schema"

        # 3. Fallback: the query parsed and ran, but returned an empty set
        #    or rows that don't match the question's expected sense
        #    (treat as semantic). Also covers type-mismatch on execution.
        if (
            "datatype mismatch" in e
            or "type mismatch" in e
            or "cannot" in e
            or "incompatible" in e
        ):
            return "semantics"

        # Empty result on a question that clearly expects non-empty rows
        # (a minimal heuristic: "list", "show", "find", "what", "who",
        #  "how many", "name").
        empty_result_keywords = ("list", "show", "find", "what", "who", "name", "how many")
        if e == "" and any(k in q for k in empty_result_keywords):
            return "semantics"

        # Default to schema as the safest repair target.
        return "schema"