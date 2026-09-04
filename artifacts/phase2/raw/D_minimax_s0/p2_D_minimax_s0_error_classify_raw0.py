"""Harness that classifies SQL execution failures (syntax/schema/semantics) and applies targeted fixes across up to two retry rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0ErrorClassify(SQLHarness):
    # Heuristic signals for error classification
    _SYNTAX_TOKENS = (
        "syntax error", "syntax", "near \"", "near '", "unterminated",
        "unexpected token", "unexpected", "parse error", "parse",
        "unrecognized token", "lexical", "malformed", "incomplete",
        "invalid input syntax", "input syntax", "you have an error in your sql",
    )
    _SCHEMA_TOKENS = (
        "no such column", "no such table", "no such column:", "no such table:",
        "no such function", "column ", "table ", "does not exist",
        "unknown column", "unknown table", "ambiguous column",
        "ambiguous", "must appear in the group by", "not found",
        "schema", "relation \"", "relation '", "relation does not exist",
        "table not found", "field not found", "cannot find",
        "no column named", "no table named",
    )
    _SEMANTIC_TOKENS = (
        "type mismatch", "datatype mismatch", "data type", "cannot be cast",
        "operator does not exist", "invalid operation", "division by zero",
        "integer overflow", "out of range", "null value in column",
        "violates not-null", "not-null constraint", "violates foreign key",
        "foreign key", "constraint", "subquery returns more than",
        "more than one row", "cannot insert", "cannot update", "cannot delete",
        "value too long", "string function", "permission denied",
        "insufficient privilege", "order by", "group by", "having",
        "aggregate", "count(", "sum(", "join", "no rows",
        "no result", "empty result", "timeout", "time limit",
    )

    def solve(self, question: str) -> str:
        schema = self.schema or ""

        # --- Round 0: initial generation ---
        sql = self._generate_sql(question, schema, attempt=0)
        result = self.execute(sql)
        if result.get("ok"):
            return self._clean_sql(sql)

        # --- Classification + fix loop (up to 2 retries) ---
        last_sql = sql
        for round_idx in range(1, 3):  # rounds 1 and 2
            err_msg = (result.get("error") or "").strip()
            err_class = self._classify_error(err_msg)
            last_sql = self._fix_sql(
                question=question,
                schema=schema,
                bad_sql=last_sql,
                err_class=err_class,
                err_msg=err_msg,
                attempt=round_idx,
            )
            result = self.execute(last_sql)
            if result.get("ok"):
                return self._clean_sql(last_sql)

        # All rounds exhausted; return the most recent attempt.
        return self._clean_sql(last_sql)

    # ------------------------- generation -------------------------

    def _generate_sql(self, question: str, schema: str, attempt: int) -> str:
        if attempt == 0:
            system = (
                "You are a precise Text-to-SQL generator. "
                "Return exactly one SQL statement and nothing else. "
                "Do not wrap the SQL in code fences or add explanations."
            )
            prompt = (
                f"### Schema\n{schema}\n\n"
                f"### Question\n{question}\n\n"
                "### SQL\n"
            )
        else:
            # Fallback (shouldn't usually trigger since we call _fix_sql directly)
            system = (
                "You are a precise Text-to-SQL generator. "
                "Return exactly one corrected SQL statement."
            )
            prompt = (
                f"### Schema\n{schema}\n\n"
                f"### Question\n{question}\n\n### SQL\n"
            )
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(raw)

    # ------------------------ classification ----------------------

    def _classify_error(self, err_msg: str) -> str:
        e = (err_msg or "").lower()
        if not e:
            return "semantic"

        syntax_score = self._count_hits(e, self._SYNTAX_TOKENS)
        schema_score = self._count_hits(e, self._SCHEMA_TOKENS)
        semantic_score = self._count_hits(e, self._SEMANTIC_TOKENS)

        # Priority order: syntax > schema > semantic, since syntax errors
        # often mask deeper issues and must be fixed first.
        if syntax_score and syntax_score >= schema_score and syntax_score >= semantic_score:
            return "syntax"
        if schema_score >= semantic_score and schema_score > 0:
            return "schema"
        if semantic_score > 0:
            return "semantic"

        # Disambiguation fallback: keywords that strongly imply one class.
        if "syntax" in e or "parse" in e or "unexpected token" in e:
            return "syntax"
        if "does not exist" in e or "no such" in e or "unknown column" in e or "unknown table" in e:
            return "schema"
        return "semantic"

    @staticmethod
    def _count_hits(text: str, tokens) -> int:
        return sum(1 for t in tokens if t in text)

    # ---------------------------- fix -----------------------------

    def _fix_sql(
        self,
        question: str,
        schema: str,
        bad_sql: str,
        err_class: str,
        err_msg: str,
        attempt: int,
    ) -> str:
        if err_class == "syntax":
            prompt = self._syntax_prompt(question, schema, bad_sql, err_msg)
        elif err_class == "schema":
            prompt = self._schema_prompt(question, schema, bad_sql, err_msg)
        else:  # semantic
            prompt = self._semantic_prompt(question, schema, bad_sql, err_msg)

        system = (
            "You are a precise Text-to-SQL repair engine. "
            "Diagnose the reported error and return exactly one corrected SQL "
            "statement with no commentary and no code fences."
        )
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(raw)

    def _syntax_prompt(self, question, schema, bad_sql, err_msg):
        return (
            "### Error Class\n"
            "SYNTAX\n\n"
            "### Database Error\n"
            f"{err_msg}\n\n"
            "### Previous (Broken) SQL\n"
            f"{bad_sql}\n\n"
            "### Instruction\n"
            "The SQL above has a SYNTAX error. Rewrite it into a single valid "
            "SQL statement. Preserve the original intent. Fix quoting, "
            "parentheses, commas, trailing tokens, reserved-word misuse, and "
            "malformed clauses. Do not change table or column names unless the "
            "originals were themselves syntactically invalid.\n\n"
            "### Schema\n"
            f"{schema}\n\n"
            "### Question\n"
            f"{question}\n\n"
            "### Corrected SQL\n"
        )

    def _schema_prompt(self, question, schema, bad_sql, err_msg):
        return (
            "### Error Class\n"
            "SCHEMA\n\n"
            "### Database Error\n"
            f"{err_msg}\n\n"
            "### Previous (Broken) SQL\n"
            f"{bad_sql}\n\n"
            "### Instruction\n"
            "The SQL above references objects (tables/columns/functions) that "
            "do not exist or are ambiguous. Cross-reference the schema below "
            "and produce a corrected SQL that uses ONLY tables and columns "
            "present in the schema. Resolve ambiguity with fully qualified "
            "names (schema.table.column). Keep the same intent.\n\n"
            "### Schema\n"
            f"{schema}\n\n"
            "### Question\n"
            f"{question}\n\n"
            "### Corrected SQL\n"
        )

    def _semantic_prompt(self, question, schema, bad_sql, err_msg):
        return (
            "### Error Class\n"
            "SEMANTICS\n\n"
            "### Database Error\n"
            f"{err_msg}\n\n"
            "### Previous (Broken) SQL\n"
            f"{bad_sql}\n\n"
            "### Instruction\n"
            "The SQL above is syntactically valid and references real schema "
            "objects, but it fails semantically (type mismatch, aggregation / "
            "GROUP BY misuse, join cardinality, subquery arity, NULL handling, "
            "predicate logic, etc.). Rewrite it so it executes successfully "
            "while preserving the user's intent. Do not invent tables or "
            "columns.\n\n"
            "### Schema\n"
            f"{schema}\n\n"
            "### Question\n"
            f"{question}\n\n"
            "### Corrected SQL\n"
        )

    # -------------------------- cleanup ---------------------------

    @staticmethod
    def _clean_sql(sql: str) -> str:
        if sql is None:
            return ""
        s = sql.strip()
        # Strip trailing semicolons for canonical form.
        while s.endswith(";"):
            s = s[:-1].rstrip()
        return s