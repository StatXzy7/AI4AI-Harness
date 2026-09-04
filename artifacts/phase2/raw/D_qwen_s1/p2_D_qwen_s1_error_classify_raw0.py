"""Executes generated SQL, classifies failures as syntax, schema, or semantics, and applies class-specific repairs for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS1ErrorClassify(SQLHarness):
    MAX_REPAIR_ROUNDS = 2

    def solve(self, question: str) -> str:
        try:
            schema = self.schema
        except Exception:
            schema = ""
        schema = str(schema or "")

        sql = self._extract_sql(
            self._llm(self._initial_prompt(question, schema), self._initial_system())
        )
        result = self._safe_execute(sql)
        if self._is_ok(result):
            return sql

        attempts = [
            {
                "sql": sql,
                "error": self._error_text(result),
                "category": self._classify_failure(sql, result),
            }
        ]

        for round_idx in range(self.MAX_REPAIR_ROUNDS):
            category = attempts[-1].get("category") or "semantics"

            if category == "syntax":
                raw = self._repair_syntax(question, schema, sql, result, attempts, round_idx)
            elif category == "schema":
                raw = self._repair_schema(question, schema, sql, result, attempts, round_idx)
            else:
                raw = self._repair_semantic(question, schema, sql, result, attempts, round_idx)

            candidate = self._extract_sql(raw)
            if not candidate:
                candidate = sql

            if any(self._same_sql(candidate, attempt["sql"]) for attempt in attempts):
                sql = candidate
                break

            sql = candidate
            result = self._safe_execute(sql)
            if self._is_ok(result):
                return sql

            attempts.append(
                {
                    "sql": sql,
                    "error": self._error_text(result),
                    "category": self._classify_failure(sql, result),
                }
            )

        return sql

    def _initial_system(self) -> str:
        return "You are an expert Text-to-SQL system. Output only one valid SQL statement."

    def _initial_prompt(self, question: str, schema: str) -> str:
        return (
            "Use the schema below to write one SQL query that answers the question.\n"
            "Return only SQL; no explanation, no markdown.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n"
        )

    def _repair_syntax(self, question: str, schema: str, sql: str, result: dict, attempts: list, round_idx: int) -> str:
        previous = self._format_attempts(attempts[:-1])
        prompt = f"""Repair round {round_idx + 1}.
The SQL query below failed with a syntax error. Repair only the syntax problem.
Preserve the original intent, tables, columns, filters, and projection.

Schema:
{schema}

Question:
{question}

Current SQL:
{sql or "No SQL was generated."}

Syntax error:
{self._error_text(result)}
"""
        if previous:
            prompt += f"\nPrevious attempts:\n{previous}\n"
        prompt += "\nReturn only the corrected SQL query."
        return self._llm(prompt, system="You are a precise SQL syntax repair tool. Output only valid SQL.")

    def _repair_schema(self, question: str, schema: str, sql: str, result: dict, attempts: list, round_idx: int) -> str:
        previous = self._format_attempts(attempts[:-1])
        prompt = f"""Repair round {round_idx + 1}.
The SQL query below failed because a table, column, or identifier is not valid for the schema.
Fix schema references only: use exact names from the schema, correct misspellings, qualify columns, and adjust aliases.
Do not invent tables or columns and do not change the question intent.

Schema:
{schema}

Question:
{question}

Current SQL:
{sql or "No SQL was generated."}

Schema error:
{self._error_text(result)}
"""
        if previous:
            prompt += f"\nPrevious attempts:\n{previous}\n"
        prompt += "\nReturn only the corrected SQL query."
        return self._llm(prompt, system="You are a SQL schema-mapping repair tool. Output only valid SQL using schema names.")

    def _repair_semantic(self, question: str, schema: str, sql: str, result: dict, attempts: list, round_idx: int) -> str:
        previous = self._format_attempts(attempts[:-1])
        prompt = f"""Repair round {round_idx + 1}.
The SQL query below failed because of semantic or logical misuse.
Fix aggregation/grouping, type compatibility, scalar subqueries, join conditions, or other semantic problems so the query executes and answers the question.

Schema:
{schema}

Question:
{question}

Current SQL:
{sql or "No SQL was generated."}

Semantic error:
{self._error_text(result)}
"""
        if previous:
            prompt += f"\nPrevious attempts:\n{previous}\n"
        prompt += "\nReturn only the corrected SQL query."
        return self._llm(prompt, system="You are a SQL semantic repair tool. Output only valid SQL.")

    def _format_attempts(self, attempts: list) -> str:
        if not attempts:
            return ""
        blocks = []
        for i, attempt in enumerate(attempts, 1):
            blocks.append(
                f"Attempt {i}:\n"
                f"SQL: {attempt.get('sql', '')}\n"
                f"Error: {attempt.get('error', '')}\n"
                f"Category: {attempt.get('category', 'semantics')}"
            )
        return "\n\n".join(blocks)

    def _classify_failure(self, sql: str, result: dict) -> str:
        error = self._error_text(result).lower()
        if not error:
            return "semantics"
        if self._is_schema_error(error):
            return "schema"
        if self._is_syntax_error(error):
            return "syntax"
        if self._is_semantic_error(error):
            return "semantics"
        if self._has_syntax_shape(sql):
            return "syntax"
        return "semantics"

    def _is_schema_error(self, error: str) -> bool:
        direct_markers = (
            "no such table",
            "no such column",
            "no such field",
            "unknown table",
            "unknown column",
            "unknown field",
            "unknown identifier",
            "table not found",
            "column not found",
            "field not found",
            "object not found",
            "invalid table",
            "invalid column",
            "invalid identifier",
            "undefined table",
            "undefined column",
            "undefined relation",
            "relation does not exist",
            "table does not exist",
            "column does not exist",
            "not a valid table",
            "not a valid column",
            "not a valid identifier",
            "missing table",
            "missing column",
            "missing field",
        )
        if any(marker in error for marker in direct_markers):
            return True
        if "does not exist" in error and any(
            word in error for word in ("table", "column", "relation", "field", "database", "schema")
        ):
            return True
        if "not found" in error and any(
            word in error for word in ("table", "column", "relation", "field", "object")
        ):
            return True
        if "unknown" in error and any(
            word in error for word in ("table", "column", "field", "identifier")
        ):
            return True
        return False

    def _is_syntax_error(self, error: str) -> bool:
        markers = (
            "syntax",
            "parse",
            "parsing",
            "incomplete input",
            "unexpected",
            "near",
            "token",
            "unrecognized",
            "malformed",
            "illegal",
            "unclosed",
            "unterminated",
            "missing",
            "invalid sql",
            "invalid query",
            "compile",
            "compilation",
            "bad request",
        )
        return any(marker in error for marker in markers)

    def _is_semantic_error(self, error: str) -> bool:
        markers = (
            "group by",
            "aggregate",
            "aggregation",
            "type mismatch",
            "datatype",
            "data type",
            "conversion",
            "cast",
            "cannot convert",
            "division by zero",
            "subquery",
            "more than one row",
            "wrong number of arguments",
            "too many arguments",
            "too few arguments",
            "invalid use of",
            "not allowed",
            "must appear in",
            "isn't in group by",
            "not in group by",
            "window function",
            "constraint",
            "foreign key",
            "unique",
            "null",
            "out of range",
            "operator does not exist",
            "function does not exist",
            "no such function",
            "ambiguous",
            "correlated",
            "argument",
            "distinct",
            "having",
            "limit",
            "offset",
            "order by",
            "cartesian",
            "cross join",
            "permission",
            "read-only",
            "read only",
            "transaction",
            "lock",
            "timeout",
        )
        return any(marker in error for marker in markers)

    def _has_syntax_shape(self, sql: str) -> bool:
        normalized = (sql or "").strip().lower()
        if not normalized:
            return True
        if normalized.count("(") != normalized.count(")"):
            return True
        if not any(keyword in normalized for keyword in ("select", "with", "insert", "update", "delete")):
            return True
        return False

    def _llm(self, prompt: str, system: str) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            try:
                response = self.llm(prompt)
            except Exception:
                return ""
        except Exception:
            return ""
        return self._to_text(response)

    def _to_text(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            parts = [self._to_text(item) for item in value]
            return "\n".join(part for part in parts if part)
        if isinstance(value, dict):
            choices = value.get("choices")
            if choices:
                first = choices[0] if isinstance(choices, (list, tuple)) and choices else None
                if first is not None:
                    return self._to_text(first)
            for key in ("text", "content", "output", "completion", "message", "sql", "response"):
                if key in value:
                    return self._to_text(value[key])
            return str(value)

        choices = getattr(value, "choices", None)
        if choices:
            try:
                first = choices[0]
            except Exception:
                first = None
            if first is not None:
                return self._to_text(first)
        for attr in ("text", "content", "output", "completion", "message", "sql", "response"):
            if hasattr(value, attr):
                return self._to_text(getattr(value, attr))
        return str(value)

    def _extract_sql(self, text) -> str:
        raw = self._to_text(text)
        try:
            extracted = bridge.extract_sql(raw)
        except Exception:
            extracted = ""
        if extracted:
            return self._postprocess_sql(self._to_text(extracted))
        return self._postprocess_sql(self._fallback_sql(raw))

    def _fallback_sql(self, raw: str) -> str:
        raw = self._to_text(raw)
        if not raw:
            return ""
        if "