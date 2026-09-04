"""Generate SQL, execute it, classify execution failures as syntax/schema/semantics, and apply class-specific repairs for up to two repair rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS2ErrorClassify(SQLHarness):
    _MAX_REPAIR_ROUNDS = 2

    _SCHEMA_ERROR_MARKERS = (
        "no such table",
        "no such column",
        "unknown column",
        "unknown table",
        "column not found",
        "table not found",
        "does not exist",
        "invalid column name",
        "invalid table name",
        "ambiguous column",
        "not a valid table",
        "not a valid column",
        "cannot resolve",
        "cannot find",
        "unrecognized column",
        "undefined column",
        "undefined table",
        "object not found",
        "schema",
    )

    _SYNTAX_ERROR_MARKERS = (
        "syntax",
        "near \"",
        "near '",
        "incomplete input",
        "unrecognized token",
        "malformed",
        "unterminated",
        "expected",
        "missing",
        "parse",
        "invalid token",
        "unexpected",
        "unbalanced",
        "parenthesis",
        "syntax error",
        "unrecognized",
    )

    _SEMANTIC_ERROR_MARKERS = (
        "no such function",
        "wrong number of arguments",
        "datatype mismatch",
        "type mismatch",
        "aggregate",
        "group by",
        "misuse",
        "division by zero",
        "constraint",
        "foreign key",
        "unique",
        "subquery returns more than 1",
        "operand",
        "conversion",
        "overflow",
        "invalid use",
        "not allowed",
        "function",
        "argument",
        "logic",
        "collation",
    )

    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        sql = self._initial_sql(question, schema)
        last_sql = sql

        for stage in range(self._MAX_REPAIR_ROUNDS + 1):
            result = self._safe_execute(sql)

            if result.get("ok"):
                return sql

            last_sql = sql
            error = str(result.get("error") or "Execution failed")
            failure_class = self._classify_error(error, sql)

            if stage == self._MAX_REPAIR_ROUNDS:
                break

            repaired = self._repaired_sql(
                question=question,
                schema=schema,
                previous_sql=sql,
                error=error,
                failure_class=failure_class,
            )

            if not repaired or self._normalize_sql(repaired) == self._normalize_sql(sql):
                break

            sql = repaired

        return last_sql

    def _initial_sql(self, question: str, schema: str) -> str:
        system = (
            "You are an expert SQLite SQL writer. "
            "Output one complete, executable SELECT statement only."
        )
        prompt = f"""Use the schema below to answer the question.

Schema:
{schema}

Question:
{question}

Return only one executable SQLite SELECT statement."""
        return self._extract_sql(self._llm_text(prompt, system=system))

    def _repaired_sql(
        self,
        question: str,
        schema: str,
        previous_sql: str,
        error: str,
        failure_class: str,
    ) -> str:
        guidance, system = self._repair_guidance(failure_class)

        prompt = f"""Schema:
{schema}

Question:
{question}

Previous SQL:
{previous_sql or "NONE"}

Execution error:
{error or "UNKNOWN"}

Failure class:
{failure_class}

Repair guidance:
{guidance}

Return only the corrected SQLite SELECT statement."""

        return self._extract_sql(self._llm_text(prompt, system=system))

    def _repair_guidance(self, failure_class: str):
        if failure_class == "syntax":
            guidance = (
                "Fix the syntax error while preserving the intended tables, columns, filters, joins, and aggregations. "
                "Check commas, parentheses, quotation marks, aliases, clause order, and statement termination."
            )
            system = (
                "You are an expert SQLite debugger. "
                "Fix only syntax problems and output one corrected SELECT statement only."
            )
            return guidance, system

        if failure_class == "schema":
            guidance = (
                "Fix invalid schema references. Use only tables and columns that appear in the provided schema, "
                "with exact names. Qualify columns when needed, correct aliases, and remove or replace nonexistent "
                "tables or columns."
            )
            system = (
                "You are an expert SQLite debugger. "
                "Fix schema-reference problems using the provided schema and output one corrected SELECT statement only."
            )
            return guidance, system

        guidance = (
            "Fix semantic/logic errors. Ensure joins, filters, grouping, aggregation, DISTINCT, ORDER BY, LIMIT, "
            "and expressions are valid in SQLite and correctly answer the question. Use valid built-in functions "
            "and correct argument counts."
        )
        system = (
            "You are an expert SQLite debugger. "
            "Fix semantic/logic problems and output one corrected SELECT statement only."
        )
        return guidance, system

    def _classify_error(self, error: str, sql: str) -> str:
        if not (sql or "").strip():
            return "syntax"

        err = (error or "").lower()
        if not err:
            return "semantics"

        if any(marker in err for marker in self._SCHEMA_ERROR_MARKERS):
            return "schema"

        if any(marker in err for marker in self._SYNTAX_ERROR_MARKERS):
            return "syntax"

        if any(marker in err for marker in self._SEMANTIC_ERROR_MARKERS):
            return "semantics"

        if "no such" in err or "not found" in err or "does not exist" in err:
            return "schema"

        if "near" in err or "token" in err or "syntax" in err:
            return "syntax"

        return "semantics"

    def _safe_execute(self, sql: str) -> dict:
        candidate = (sql or "").strip()
        if not candidate:
            return {"ok": False, "rows": [], "error": "Empty SQL"}

        try:
            result = self.execute(candidate)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": str(result)}

        return {
            "ok": bool(result.get("ok")),
            "rows": result.get("rows", []),
            "error": str(result.get("error") or ""),
        }

    def _extract_sql(self, text: str) -> str:
        raw = text or ""

        try:
            sql = bridge.extract_sql(raw)
        except Exception:
            sql = ""

        sql = (sql or "").strip().rstrip(";").strip()
        if sql:
            return sql

        return self._fallback_extract_sql(raw)

    def _fallback_extract_sql(self, text: str) -> str:
        if not text:
            return ""

        if "